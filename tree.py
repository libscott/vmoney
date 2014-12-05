import os.path
import pygit2
import sys


class DataTree(object):

    alice = pygit2.Signature('Alice Author', 'alice@authors.tld')
    cecil = pygit2.Signature('Cecil Committer', 'cecil@committers.tld')

    def __init__(self, branch_name, repo, author=alice, committer=cecil):
        self.ref_name = branch_name
        self.repo = repo
        self.author = author
        self.committer = committer
        self.tree = repo.lookup_reference(branch_name).peel().tree

    @classmethod
    def discover(cls):
        repodir = pygit2.discover_repository('.')
        repo = pygit2.Repository(repodir)
        return cls(repo.head.name, repo)

    def branch(self, name, force=False):
        branch = self.repo.create_branch(name, self.repo.head.peel(), force)
        return DataTree(branch.name, self.repo)

    def __contains__(self, path):
        return path in self.tree

    def get_blob(self, path):
        if path in self:
            input_ = self.tree[path]
            blob = self.repo.get(input_.id)
            return blob.read_raw()
        return ''

    def get_list(self, path):
        if path in self:
            parent = self.tree[path]
            entries = self.repo.get(parent.oid)
            return [os.path.join(path, e.name) for e in entries]
        return []

    def __getitem__(self, item):
        if type(item) == int:
            return super(DataTree, self).__getitem__(item)
        else:
            return self.get_blob(item)

    def __setitem__(self, path, value):
        path = path.split('/')

        def get_tree_builder(path):
            oid = None
            if path:
                if path in self.tree:
                    oid = self.tree[path].oid
                else:
                    return self.repo.TreeBuilder()
            else:
                oid = self.tree.oid
            return self.repo.TreeBuilder(oid)

        basename = path.pop()

        builder = get_tree_builder('/'.join(path))
        if value != None:
            blob_id = self.repo.create_blob(value)
            builder.insert(basename, blob_id, pygit2.GIT_FILEMODE_BLOB)
        else:
            builder.remove(basename)

        while path:
            name = path.pop()
            child_oid = builder.write()
            builder = get_tree_builder('/'.join(path))
            builder.insert(name, child_oid, pygit2.GIT_FILEMODE_TREE)

        self.tree = self.repo.get(builder.write())

    def __delitem__(self, path):
        self[path] = None

    def commit(self, msg):
        ref = self.repo.lookup_reference(self.ref_name)
        parent = ref.peel().id
        self.repo.create_commit( self.ref_name
                               , self.author
                               , self.committer
                               , msg
                               , self.tree.oid
                               , [parent]
                               )
