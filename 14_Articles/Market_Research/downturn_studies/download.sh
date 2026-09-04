#!/bin/bash
# Download all open-access study PDFs, validating each is a real PDF (%PDF header).
cd /home/fields/Fields_Orchestrator/14_Articles/Market_Research/downturn_studies
DIR=pdfs
mkdir -p "$DIR"
UA="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"
OK=0; FAIL=0
: > download_failures.txt
while IFS=$'\t' read -r fname url; do
  [ -z "$fname" ] && continue
  out="$DIR/$fname"
  if [ -s "$out" ] && head -c4 "$out" | grep -q '%PDF'; then
    echo "SKIP (have) $fname"; OK=$((OK+1)); continue
  fi
  curl -sL --max-time 90 -A "$UA" -e "https://www.google.com/" -o "$out" "$url"
  if [ -s "$out" ] && head -c4 "$out" | grep -q '%PDF'; then
    sz=$(du -h "$out" | cut -f1)
    echo "OK   [$sz] $fname"; OK=$((OK+1))
  else
    echo "FAIL       $fname  <- $url"
    echo -e "$fname\t$url" >> download_failures.txt
    rm -f "$out"
    FAIL=$((FAIL+1))
  fi
done < download_manifest.tsv
echo "-----"
echo "OK=$OK  FAIL=$FAIL"
