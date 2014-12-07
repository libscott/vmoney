#!/usr/bin/env python

import argparse
import base58
import collections
import ecdsa
import hashlib
import json
import os.path
import sys

from tree import tree_changes, discover_head


AppContext = collections.namedtuple('AppContext', 'head,sk,address')

Input = collections.namedtuple('Input', 'owner,txid,amount')


def send(args):
    ctx = get_ctx(args)
    amount = get_amount(args.amount)
    recip = args.address

    txid, mods = create_tx(ctx.address, recip, amount, ctx.head.tree)

    sig = ctx.sk.sign_deterministic(txid)
    vk = ctx.sk.get_verifying_key()

    tx = json.dumps({
        'to': recip,
        'pubkey': base58.b58encode(vk.to_der()),
        'sig': base58.b58encode(sig),
        'txid': txid,
        'amount': amount,
    }, sort_keys=True, indent=4)
    mods.append(('data/%s/tx' % ctx.address, tx))

    branch_name = 'tx/%s' % txid
    branch = ctx.head.branch(branch_name, force=True)

    for k, v in mods:
        branch[k] = v

    msg = "%s sent %s bits to %s" % ( ctx.address
                                    , amount
                                    , recip
                                    )
    branch.commit(msg)
    os.system('git merge ' + branch_name)


class ValidationError(AssertionError):
    pass


class InsufficientFunds(ValidationError):
    pass


def create_tx(sender, recip, amount, tree, mint=False):
    """ Get txid and list of modifications to make to a tree. """
    inputs = []
    change = -1

    if mint:
        change = 0
    else:
        for inp in get_spendable_inputs(sender, tree):
            inputs.append(inp)
            change = sum(i.amount for i in inputs) - amount
            if change >= 0:
                break

    if change < 0:
        raise InsufficientFunds()

    input_txids = []
    for inp in inputs:
        input_txids.append(inp.txid)

    txid = get_txid(input_txids)

    mods = []

    for input_txid in input_txids:
        mods.append(('data/%s/balance/%s' % (sender, input_txid), None))

    deposit_path = 'data/%s/balance/%s' % (recip, txid)
    mods.append((deposit_path, json.dumps({'amount': amount})))

    if change:
        change_path = 'data/%s/balance/%s' % (sender, txid)
        mods.append((change_path, json.dumps({'amount': change})))

    return txid, mods


def validate_tx(parent, commit):
    """ Validate that a transaction is correct by replaying it against parent tree """
    # Get changes
    data1 = parent.tree.subtree_or_empty('data')
    data2 = commit.tree.subtree_or_empty('data')
    changes = list(tree_changes(data1, data2))
    if not changes:
        return None
    # find transaction
    sender = None
    for key, change in changes:
        if len(key) == 2 and key[1] == 'tx':
            sender = key[0]
            break
    assert sender, "Illegal transaction; no tx file"
    txfile = 'data/%s/tx' % sender
    txdata = commit.tree.get(txfile)
    tx = json.loads(txdata)
    # Make sure tx looks ok ish
    """ here's where we would validate the structure of
        the tx, if we were making a real cryptocurrency """
    txid, mods = create_tx(sender, tx['to'], tx['amount'], parent.tree)
    # Verify signature
    pubkey = base58.b58decode(tx['pubkey'])
    sig = base58.b58decode(tx['sig'])
    ecdsa.VerifyingKey.from_der(pubkey).verify(sig, txid)
    # Reconstruct changes to tree (intermediary objects bloat object store)
    mods.append((txfile, txdata))
    tree = parent.tree
    for k, v in mods:
        tree = tree.set(k, v)
    assert tree == commit.tree, "Tree reconstruction failed"
    tx['from'] = sender
    return tx


def get_txid(input_txids):
    tohash = ''.join(sorted(input_txids))
    return base58.b58encode(hashlib.sha256(tohash).digest())


def get_amount(dat):
    amount = int(dat)
    if amount < 1:
        raise ValueError("Amount must be >= 1")
    return amount


def balance(args):
    ctx = get_ctx(args)
    inputs = get_spendable_inputs(ctx.address, ctx.head.tree)
    print "%s: %s bits" % (ctx.address, sum(i.amount for i in inputs))


def get_spendable_inputs(address, tree):
    balances_path = 'data/%s/balance' % address
    tree = tree.subtree_or_empty(balances_path)
    names = [entry.name for entry in tree]
    names.sort()
    for txid in names:
        input_data = json.loads(tree.get(txid))
        yield Input(address, txid, input_data['amount'])


def get_ctx(args):
    # data tree
    db = discover_head()
    # address
    keyfile = os.path.expanduser(args.keyfile)
    if not os.path.exists(keyfile):
        print >>sys.stderr, ("Keyfile at %s does not exist, generating new key" % keyfile)
        sk = ecdsa.SigningKey.generate()
        open(keyfile, 'w').write(sk.to_pem())
    sk = ecdsa.SigningKey.from_pem(open(keyfile).read())
    vk = sk.get_verifying_key()
    address_sha = hashlib.sha256(vk.to_der()).digest()
    address = 'V' + base58.b58encode(address_sha)[:10]
    return AppContext(db, sk, address)


def txlog(args):
    ctx = get_ctx(args)
    commit = None
    for parent in ctx.head.log():
        if commit:
            try:
                tx = validate_tx(parent, commit)
                print commit.oid, tx
            except AssertionError as e:
                print repr(e)
        commit = parent


def validate(args):
    import pdb; pdb.set_trace()
    1


parser = argparse.ArgumentParser(description='Verne (toy) money')
parser.add_argument('-k', '--keyfile', default='~/.vmoney')
subparsers = parser.add_subparsers()

parser_balance = subparsers.add_parser('balance', help='Show balance')
parser_balance.set_defaults(func=balance)

parser_send = subparsers.add_parser('send', help='Send bits')
parser_send.add_argument('--mint', action='store_true', help='create money')
parser_send.add_argument('amount')
parser_send.add_argument('address')
parser_send.set_defaults(func=send)

parser_validate = subparsers.add_parser('validate', help='Validate given reference')
parser_validate.add_argument('ref')
parser_validate.set_defaults(func=validate)

parser_log = subparsers.add_parser('txlog', help='Show transaction log')
parser_log.set_defaults(func=txlog)


def main():
    args = parser.parse_args()
    args.func(args)


if __name__ == '__main__':
    main()
