import pygit2


class Commit(object):
    def __init__(self, repo, pygit2_commit):
        self._commit = pygit2_commit
        self.repo = repo

    @property
    def tree(self):
        return Tree(self.repo, self._commit.tree)

    def log(self):
        log_ = self.repo.walk(self._commit.oid, pygit2.GIT_SORT_TIME)
        return (Commit(self.repo, c) for c in log_)

    def branch(self, name, force=False):
        branch = self.repo.create_branch(name, self._commit, force)
        return Branch(self.repo, branch.name)


class Tree(object):
    def __init__(self, repo, pygit2_tree):
        self._tree = pygit2_tree
        self.repo = repo

    _ERROR = object()

    def get(self, path, default=_ERROR):
        if path in self._tree:
            entry = self._tree[path]
            if entry.filemode == pygit2.GIT_FILEMODE_BLOB:
                blob = self.repo.get(entry.id)
                return blob.read_raw()
        if default is self._ERROR:
            raise KeyError(path)
        return default

    def subtree(self, path):
        entry = self._tree[path]
        if entry.filemode == pygit2.GIT_FILEMODE_TREE:
            tree = self.repo.get(entry.id)
            return Tree(self.repo, tree)
        raise KeyError(path)

    def subtree_or_empty(self, path):
        try:
            return self.subtree(path)
        except KeyError:
            empty = self.repo.TreeBuilder()
            tree = self.repo.get(empty.write())
            return Tree(self.repo, tree)

    def set(self, path, data):
        """
        Return a new tree inheriting from this tree, setting or updating
        a given path.
        """
        parts = path.split('/')
        basename = parts.pop()

        # The first builder is the bottom tree that references our given
        # leaf node.
        builder = self._get_tree_builder('/'.join(parts))
        if data == None:
            builder.remove(basename)
        else:
            blob_id = self.repo.create_blob(data)
            builder.insert(basename, blob_id, pygit2.GIT_FILEMODE_BLOB)

        # Now we replace all the parent trees to point to our new tree
        # until we hit the root.
        while parts:
            name = parts.pop()
            child_oid = builder.write()
            builder = self._get_tree_builder('/'.join(parts))
            builder.insert(name, child_oid, pygit2.GIT_FILEMODE_TREE)

        tree = self.repo.get(builder.write())
        return Tree(self.repo, tree)

    def __contains__(self, path):
        return path in self._tree

    def _get_tree_builder(self, path):
        oid = None
        if path:
            if path in self._tree:
                oid = self._tree[path].oid
            else:
                return self.repo.TreeBuilder()
        else:
            oid = self._tree.oid
        return self.repo.TreeBuilder(oid)

    def __iter__(self):
        return iter(self._tree)

    def __eq__(self, other):
        return self._tree.oid == other._tree.oid


def flatten_tree(tree, prefix=()):
    """ Flatten a tree into name -> entry pairs """
    for entry in tree._tree:
        name = prefix + (entry.name,)
        if entry.filemode == pygit2.GIT_FILEMODE_TREE:
            subtree = tree.subtree(entry.name)
            for item in flatten_tree(subtree, name):
                yield item
        else:
            yield (name, entry)


def dict_diff(dict1, dict2):
    """
    Combine a dictionary, discarding entries that are the same
    in both left and right
    """
    for key in set(dict1.keys() + dict2.keys()):
        item1 = dict1.get(key)
        item2 = dict2.get(key)
        if item1 != item2:
            yield (key, (item1, item2))


def tree_changes(tree1, tree2):
    """ Iterate changes between 2 trees """
    return dict_diff(dict(flatten_tree(tree1)), dict(flatten_tree(tree2)))


def discover_head():
    repodir = pygit2.discover_repository('.')
    repo = pygit2.Repository(repodir)
    return Commit(repo, repo.head.peel())


class Branch(object):
    """ Mutable branch object """
    alice = pygit2.Signature('Alice Author', 'alice@authors.tld')
    cecil = pygit2.Signature('Cecil Committer', 'cecil@committers.tld')

    def __init__(self, repo, branch_name):
        self.ref_name = branch_name
        self.repo = repo
        _tree = repo.lookup_reference(self.ref_name).peel().tree
        self.tree = Tree(repo, _tree)

    @classmethod
    def discover(cls):
        repodir = pygit2.discover_repository('.')
        repo = pygit2.Repository(repodir)
        return cls(repo, repo.head.name)

    def __contains__(self, path):
        return path in self.tree

    def __getitem__(self, name):
        return self.tree[name]

    def __setitem__(self, path, value):
        self.tree = self.tree.set(path, value)

    def __delitem__(self, path):
        self[path] = None

    def commit(self, msg, author=alice, committer=cecil):
        ref = self.repo.lookup_reference(self.ref_name)
        parent = ref.peel().id
        self.repo.create_commit( self.ref_name
                               , author
                               , committer
                               , msg
                               , self.tree._tree.oid
                               , [parent]
                               )
