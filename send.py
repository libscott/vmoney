#!/usr/bin/env python

import base64
import json
import sys
import hashlib
from ecdsa import SigningKey
import verne.api
import os.path


gitcoinfile = os.path.expanduser('~/.gitcoin')

# branch
branch = verne.api.find_branch(sys.argv[1])

# get address
sk = SigningKey.from_pem(open(gitcoinfile).read())
vk = sk.get_verifying_key()
address = hashlib.sha256(vk.to_der()).hexdigest()

# get available inputs
available_inputs = []
try:
    balances = branch.tree['balances/%s' % address]
except KeyError:
    inputs = []
else:
    for entry in branch.repo.get(balances.oid):
        path = "balances/%s/%s" % (address, entry.name)
        available_inputs.append({
            'path': path,
            'name': entry.name,
            'data': json.loads(branch[path])
        })

# create tx
send = 1
to = 'a'
tx_inputs = []
tx_change = -1
for input_ in available_inputs:
    tx_inputs.append(input_)
    tx_change = sum(i['data']['amount'] for i in tx_inputs) - send
    if tx_change >= 0:
        break
assert tx_change >= 0, ("Insufficient funds to send %s" % send)

# tx id is a hash of the sorted input hashes and the last txid.
to_hash = []
for input_ in tx_inputs:
    to_hash.append(input_['name'])
    del branch[input_['path']]
txid = hashlib.sha256(''.join(sorted(to_hash))).hexdigest()
branch['balances/%s/%s' % (to, txid)] = json.dumps({'amount': send})
if tx_change:
    branch['balances/%s/%s' % (address, txid)] = json.dumps({'amount': tx_change})

# TODO: update last spent which will conflict if we try to spend the same
# outputs twice

# sign txid and commit
sig = sk.sign_deterministic(txid)
branch.commit(base64.b64encode(sig))
