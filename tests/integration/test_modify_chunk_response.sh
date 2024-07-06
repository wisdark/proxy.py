#!/bin/bash
#
# proxy.py
# ~~~~~~~~
# ⚡⚡⚡ Fast, Lightweight, Programmable, TLS interception capable
#     proxy server for Application debugging, testing and development.
#
# :copyright: (c) 2013-present by Abhinav Singh and contributors.
# :license: BSD, see LICENSE for more details.
#
# TODO: Option to also shutdown proxy.py after
# integration testing is done.  At least on
# macOS and ubuntu, pkill and kill commands
# will do the job.
#
# For github action, we simply bank upon GitHub
# to clean up any background process including
# proxy.py

PROXY_PY_PORT=$1
if [[ -z "$PROXY_PY_PORT" ]]; then
  echo "PROXY_PY_PORT required as argument."
  exit 1
fi

CERT_DIR=$2
if [[ -z "$CERT_DIR" ]]; then
  echo "CERT_DIR required as argument."
  exit 1
fi

PROXY_URL="127.0.0.1:$PROXY_PY_PORT"

# Wait for server to come up
WAIT_FOR_PROXY="lsof -i TCP:$PROXY_PY_PORT | wc -l | tr -d ' '"
while true; do
    if [[ $WAIT_FOR_PORT == 0 ]]; then
        echo "Waiting for proxy..."
        sleep 1
    else
        break
    fi
done

# Wait for http proxy and web server to start
while true; do
    curl -v \
        --max-time 1 \
        --connect-timeout 1 \
        -x $PROXY_URL \
        --cacert $CERT_DIR/ca-cert-chunk.pem \
        http://$PROXY_URL/ 2>/dev/null
    if [[ $? == 0 ]]; then
        break
    fi
    echo "Waiting for web server to start accepting requests..."
    sleep 1
done

verify_response() {
    if [ "$1" == "" ];
    then
        echo "Empty response";
        return 1;
    else
        if [ "$1" == "$2" ];
        then
            echo "Ok";
            return 0;
        else
            echo "Invalid response: '$1', expected: '$2'";
            return 1;
        fi
    fi;
}

read -r -d '' MODIFIED_CHUNK_RESPONSE << EOM
modify
chunk
response
plugin
EOM

echo "[Test ModifyChunkResponsePlugin]"
RESPONSE=$(curl -v -x $PROXY_URL --cacert $CERT_DIR/ca-cert-chunk.pem https://httpbingo.org/stream/5 2> /dev/null)
verify_response "$RESPONSE" "$MODIFIED_CHUNK_RESPONSE"
VERIFIED1=$?

EXIT_CODE=$(( $VERIFIED1 ))
exit $EXIT_CODE
