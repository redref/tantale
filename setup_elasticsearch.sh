#!/usr/bin/env bash

download() {
    echo "Downloading elasticsearch from $1..."
    curl -L -s $1 | tar xz
    echo "Downloaded"
}

is_elasticsearch_up(){
    http_code=`echo $(curl -s -o /dev/null -w "%{http_code}" "http://localhost:9200")`
    return `test $http_code = "200"`
}

wait_for_elasticsearch(){
    while ! is_elasticsearch_up; do
        sleep 3
    done
}

run() {
    echo "Starting elasticsearch ..."
    cd $1/bin
    ./elasticsearch -d -p "${1}/pidfile"
    wait_for_elasticsearch
    cd ../../
    echo "Started"
}

download_and_run() {
    url="http://download.elasticsearch.org/elasticsearch/elasticsearch/elasticsearch-$1.tar.gz"
    dir_name="$(readlink -f "elasticsearch-$1")"

    download $url

    # Run elasticsearch
    run $dir_name
}

[ "${1}" != "" ] && download_and_run "${1}" || download_and_run 2.3.1

