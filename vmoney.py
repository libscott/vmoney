#!/usr/bin/env python

import argparse
import base58
import collections
import ecdsa
import hashlib
import json
import pygit2
import os.path
import sys

from tree import tree_changes, discover_head


AppContext = collections.namedtuple('AppContext', 'head,sk,address')

Input = collections.namedtuple('Input', 'owner,txid,amount')


def send(args):
    ctx = get_ctx(args)
    amount = get_amount(args.amount)
    recipient_address = args.address
    # create tx
    inputs = []
    change = -1

    for inp in get_spendable_inputs(ctx.address, ctx.head.tree):
        inputs.append(inp)
        change = sum(i.amount for i in inputs) - amount
        if change >= 0:
            break

    if change < 0:
        print >>sys.stderr, ("Insufficient funds to send %s" % amount)
        return

    input_txids = []
    for inp in inputs:
        input_txids.append(inp.txid)

    txid = get_txid(input_txids)
    branch_name = 'tx/%s' % txid
    branch = ctx.head.branch(branch_name, force=1)

    for input_txid in input_txids:
        del branch['data/%s/balance/%s' % (ctx.address, input_txid)]

    deposit_path = 'data/%s/balance/%s' % (recipient_address, txid)
    branch[deposit_path] = json.dumps({'amount': amount})

    if change:
        change_path = 'data/%s/balance/%s' % (ctx.address, txid)
        branch[change_path] = json.dumps({'amount': change})

    # sign txid and commit
    sig = ctx.sk.sign_deterministic(txid)

    tx = json.dumps({
        'to': recipient_address,
        'sig': base58.b58encode(sig),
        'txid': txid,
        'amount': amount,
    })
    branch['data/%s/tx'] = tx

    msg = "%s sent %s bits to %s" % ( ctx.address
                                    , amount
                                    , recipient_address
                                    )
    branch.commit(msg)
    os.system('git merge ' + branch_name)


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
    for entry in tree:
        txid = entry.name
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


def parse_tx(commit, parent):
    data1 = parent.tree.subtree_or_empty('data')
    data2 = commit.tree.subtree_or_empty('data')
    changes = tree_changes(data1, data2)

    if not changes:
        return None

    sender = None
    recipient = None
    amount = 0
    inputs = []
    outputs = []
    change = -1

    for key, (old, new) in changes:
        assert len(key) == 3, ("Unrecognized key length %s" % len(key))
        (addr, cat, txid) = key
        assert cat == 'balance', ("Unrecognized category: %s)" % key)
        assert (not (old and new)), ("File modified: %s" % key)
        if old:
            inputs.append((key, json.loads(data1.get('/'.join(key)))))
        else:
            outputs.append((key, json.loads(data2.get('/'.join(key)))))

    insize  = sum(bal['amount'] for _, bal in inputs)
    outsize = sum(bal['amount'] for _, bal in outputs)

    assert insize == outsize, ("Not zero sum: %s" % (outsize - insize))
    assert insize != 0, "Zero size"

    for (key, bal) in (inputs + outputs):
        assert bal['amount'] >= 0, ("Illegal balance in %s: %s", (key, bal))

    txids = set(k[2] for k, _ in outputs)
    assert len(txids) == 1, "Multiple output txids: %s" % txids
    txid = list(txids)[0]

    input_txids = [k[2] for k, _ in inputs]
    assert len(set(input_txids)) == len(input_txids), "Input txids not unique"

    good = get_txid(input_txids)
    assert txid == good, ("Bad output txid for inputs: %s, %s" % (txid, good))

    senders = set(k[0] for k, _ in inputs)
    assert len(senders) == 1, "Multiple senders: %s" % senders
    sender = list(senders)[0]

    for (to, _, _), bal in outputs:
        if to == sender:
            assert change == -1, "Multiple change outputs"
            change = bal['amount']
        else:
            if recipient:
                assert recipient == to, "Multiple recipients"
            else:
                recipient = to
            amount += bal['amount']

    return (txid, sender, recipient, amount)



# In order to avoid all the fuss and prevent double spending, each commit
# should write a tx file with a simple data structure that can be easily
# validated. This data structure can then be applied to the parent tree,
# and the transaction will be valid if the result tree's OID is the same as the
# commit tree's OID. Weeee. <3 git.






def txlog(args):
    ctx = get_ctx(args)
    parent = None
    for commit in ctx.head.log():
        if parent:
            try:
                print parse_tx(parent, commit)
            except AssertionError as e:
                print e
        parent = commit


def validate(args):
    import pdb; pdb.set_trace()
    1


parser = argparse.ArgumentParser(description='Verne (toy) money')
parser.add_argument('-k', '--keyfile', default='~/.vmoney')
subparsers = parser.add_subparsers()

parser_balance = subparsers.add_parser('balance', help='Show balance')
parser_balance.set_defaults(func=balance)

parser_send = subparsers.add_parser('send', help='Send bits')
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
