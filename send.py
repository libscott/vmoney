#!/usr/bin/env python

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

# get balance
inputs = []
for entry in branch.tree:
    if entry.name.startswith('balances/%s/' % address):
       inputs.append(json.loads(branch[entry.name]))
balance = sum(i['amount'] for i in inputs)
print balance
