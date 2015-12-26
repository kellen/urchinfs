#!/bin/bash

for f in *.man.rst; do 
    BASE=`basename "${f}" | sed 's|\.man\.rst$||g'`
    SEC=`grep -o ":Manual section:\s*[0-9]\+" "${f}" | sed 's|:Manual section:\s*||g'`
    NEW="${BASE}.${SEC}"
    rst2man "${f}" "${NEW}" && \
    gzip "${NEW}" && \
    mkdir -p "man${SEC}" && \
    mv "${NEW}.gz" "man${SEC}"
done

echo "Done. use 'man -M ./ urchinfs' to view manpages"
