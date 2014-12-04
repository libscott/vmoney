#!/usr/bin/env python

import argparse
import base64
import collections
import ecdsa
import hashlib
import json
import os.path
import sys
import verne.branch


AppContext = collections.namedtuple('AppContext', 'db,sk,address')


Input = collections.namedtuple('Input', 'owner,txid,amount')


def send(args):
    ctx = get_ctx(args)
    print args
    return
    # create tx
    inputs = []
    change = -1
    for inp in get_spendable_inputs(ctx):
        inputs.append(inp)
        change = sum(i.amount for i in inputs) - amount
        if change >= 0:
            break

    if tx_change <= 0:
        print >>sys.stderr, ("Insufficient funds to send %s" % amount)
        return

    # tx id is a hash of the sorted input hashes.
    input_txids = []
    sha = hashlib.sha256()
    for inp in inputs:
        sha.update(inp.txid)
        del db[inp.location]

    txid = sha.hexdigest()
    deposit_path = 'data/%s/balance/%s' % (recipient_address, txid)
    ctx.db[deposit_path] = json.dumps({'amount': amount})

    if change:
        change_path = 'data/%s/balance/%s' % (ctx.address, txid)
        ctx.db[change_path] = json.dumps({'amount': change})

    # TODO: update last spent which will conflict if we try to spend the same
    # outputs twice

    # sign txid and commit
    sig = sk.sign_deterministic(txid)
    msg = "%s sent %s bits to %s\n%s" % ( ctx.address
                                        , amount
                                        , recipient_address
                                        , base64.b64encode(sig)
                                        )
    ctx.db.commit(msg)


def balance(args):
    ctx = get_ctx(args)
    inputs = get_spendable_inputs(ctx)
    print "Available balance is: %s bits" % sum(i.amount for i in inputs)


def get_spendable_inputs(ctx):
    inputs = []
    balances_path = 'data/%s/balance' % ctx.address
    for path in ctx.db.get_list(balances_path):
        input_data = json.loads(ctx.db[path])
        inp = Input(ctx.address, entry.name, input_data['amount'])
        inputs.append(inp)
    return inputs


def get_ctx(_):
    gitcoinfile = os.path.expanduser('~/.gitcoin')
    # data branch
    db = verne.branch.db_from_ref_name('refs/heads/master').branch('gitcoin_is_go', True)
    # address
    sk = ecdsa.SigningKey.from_pem(open(gitcoinfile).read())
    vk = sk.get_verifying_key()
    address = hashlib.sha256(vk.to_der()).hexdigest()
    return AppContext(db, sk, address)


parser = argparse.ArgumentParser(description='Verne toy cryptocurrency')
subparsers = parser.add_subparsers()

parser_balance = subparsers.add_parser('balance', help='Show balance')
parser_balance.set_defaults(func=balance)

parser_send = subparsers.add_parser('send', help='Send bits')
parser_send.add_argument('address')
parser_send.add_argument('amount')
parser_send.set_defaults(func=send)


def main():
    args = parser.parse_args()
    args.func(args)


if __name__ == '__main__':
    main()
