Verne Money
===========

Don't put your millions here yet.

Setup
-----

On Debian based linux:

    sudo apt-get install libssl-dev libffi-dev libgit2-dev python-pip python-virtualenv

Then:

    virtualenv .env
    source .env/bin/activate
    pip install -r requirements.txt
    ./vmoney.py balance
