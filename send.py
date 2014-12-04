#!/usr/bin/env bash

import sysgitb
import hashlib
from ecdsa import SigningKey
import verne.api

# branch
branch = verne.api.find_branch(sys.argv[1])

# get address
sk = SigningKey.from_pem(open('~/.gitcoin').read())
vk = sk.get_verifying_key()
address = hashlib.sha256(vk.to_der()).to_digest()

# get balance
import pdb; pdb.set_trace()
1
