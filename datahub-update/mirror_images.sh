#!/bin/bash

# To obtain a list of images from a templated helm chart you can use the following one-liner
# helm template <reponame>/<chartname> --version <version_number> | grep image: | sed -e 's/[ ]*image:[ ]*//' -e 's/"//g' | sort -u
# Save the output of the previous command then, for each line, add a semicolon followed by the target name and tag on adregistry (including project)
# Example line: busybox:1.31.1;adregistry.fnal.gov/monitoring/busybox:1.31.1
# This script will read that file,  pull the images for linux/amd64, re-tag them and push them into adregistry

CMD="docker"
while getopts 'f:p' flag; do
  case "${flag}" in
    f) IMAGE_FILE="${OPTARG}" ;;
    p) CMD="podman" ;;
    *) echo "Usage: $0 -f [<Path to image file>]" 1>&2 ; exit 1
       ;;
  esac
done

if [ -z "${IMAGE_FILE}" ]
then
  echo -e "ERROR: A required parameter '-f [<Path to image file>]' was not detected"
  exit 1
fi 

for entry in $(cat $IMAGE_FILE)
do 
  echo Processing - $entry
  img=$(echo $entry | awk -F ';' '{print $1}')
  registry_tag=$(echo $entry | awk -F ';' '{print $2}')
  $CMD pull --platform linux/amd64 $img
  $CMD tag $img $registry_tag
  $CMD push $registry_tag
done