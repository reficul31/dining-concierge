MASTER_NAME=NULL
MASTER_PASSWORD=NULL
DOMAIN_ENDPOINT=NULL
JSON_FILENAME=data.json

curl -XPOST -u $MASTER_NAME:$MASTER_PASSWORD $DOMAIN_ENDPOINT/_bulk --data-binary @$JSON_FILENAME -H 'Content-Type: application/json' > output.log