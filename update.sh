#!/bin/bash

UPDATE_DIR=${THE_LONE_DANCER_CACHE_DIR:-/var/run/the-lone-dancer/git}
GITHUB_URL=${THE_LONE_DANCER_GITHUB_URL:-https://github.com/morgaesis/the-lone-dancer.git}

if [[ -e $UPDATE_DIR ]]
then
	cd $UPDATE_DIR
	git pull
else
	git clone $GITHUB_URL $UPDATE_DIR
	cd $UPDATE_DIR
fi

./install.py --verbose
