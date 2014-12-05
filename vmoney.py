#!/usr/bin/env python

import argparse
import base58
import collections
import ecdsa
import hashlib
import json
import os.path
import sys

from tree import DataTree


AppContext = collections.namedtuple('AppContext', 'head,sk,address')

Input = collections.namedtuple('Input', 'owner,txid,amount')


def send(args):
    ctx = get_ctx(args)
    amount = get_amount(args.amount)
    recipient_address = args.address
    # create tx
    inputs = []
    change = -1

    for inp in get_spendable_inputs(ctx):
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

    txid = base58.b58encode(hashlib.sha256(''.join(input_txids)).digest())
    branch_name = 'tx/%s' % txid
    branch = ctx.head.branch(branch_name, force=1)

    for input_txid in input_txids:
        del branch['data/%s/balance/%s' % (ctx.address, input_txid)]

    deposit_path = 'data/%s/balance/%s' % (recipient_address, txid)
    branch[deposit_path] = json.dumps({'amount': amount})

    if change:
        change_path = 'data/%s/balance/%s' % (ctx.address, txid)
        branch[change_path] = json.dumps({'amount': change})

    # TODO: update last spent which will conflict if we try to spend the same
    # outputs twice

    # sign txid and commit
    sig = ctx.sk.sign_deterministic(txid)
    msg = "%s sent %s bits to %s\n\n%s" % ( ctx.address
                                          , amount
                                          , recipient_address
                                          , base58.b58encode(sig)
                                          )
    branch.commit(msg)
    os.system('git merge ' + branch_name)


def get_amount(dat):
    amount = int(dat)
    if amount < 1:
        raise ValueError("Amount must be >= 1")
    return amount


def balance(args):
    ctx = get_ctx(args)
    inputs = get_spendable_inputs(ctx)
    print "%s: %s bits" % (ctx.address, sum(i.amount for i in inputs))


def get_spendable_inputs(ctx):
    inputs = []
    balances_path = 'data/%s/balance' % ctx.address
    for path in ctx.head.get_list(balances_path):
        input_data = json.loads(ctx.head.get_blob(path))
        [_, _, _, txid] = path.split('/')
        inp = Input(ctx.address, txid, input_data['amount'])
        inputs.append(inp)
    return inputs


def get_ctx(args):
    # data tree
    db = DataTree.discover()
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


def log(args):
    import pdb; pdb.set_trace()
    1


def validate(args):
    import pdb; pdb.set_trace()
    1



parser = argparse.ArgumentParser(description='Verne (toy) money')
parser.add_argument('-k', '--keyfile', default='~/.gitcoin')
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

parser_log = subparsers.add_parser('log', help='Show transaction log')
parser_log.set_defaults(func=log)


def main():
    args = parser.parse_args()
    args.func(args)


if __name__ == '__main__':
    main()
