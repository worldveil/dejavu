# To run:
#   export HACK_S3_BUCKET=ken-hack
#   export HACK_S3_BUCKET=ihr-de-stg-nonprod
#   export HACK_S3_PREFIX=hackday_2019

import warnings
import json
warnings.filterwarnings("ignore")

from dejavu import Dejavu


# load config from a JSON file (or anything outputting a python dictionary)
with open("dejavu.cnf.SAMPLE") as f:
    config = json.load(f)

def pre_download_all_files_from_s3(local_downloaded_foler):
	import os
	import boto3
	client = boto3.client('s3')
	HACK_S3_BUCKET = os.environ['HACK_S3_BUCKET']
	HACK_S3_PREFIX = os.environ['HACK_S3_PREFIX']
	paginator = client.get_paginator('list_objects_v2')
	result = paginator.paginate(Bucket=HACK_S3_BUCKET, Prefix=HACK_S3_PREFIX, StartAfter='2018')
	local_downloaded_foler = os.path.join(local_downloaded_foler, HACK_S3_PREFIX)
	if not os.path.exists(local_downloaded_foler):
		print("Creating local directory...{}".format(local_downloaded_foler))
		os.makedirs(local_downloaded_foler)
	s3 = boto3.resource('s3')
	for page in result:
		if "Contents" in page:
			for key in page["Contents"]:
				keyString = key["Key"]
				print('downloading...{}'.format(keyString))
				try:
					s3.Bucket(HACK_S3_BUCKET).download_file(keyString, local_downloaded_foler + "/" + keyString)
				except Exception as e:
					print("failed....{}".format(e))


if __name__ == '__main__':

	# create a Dejavu instance
	djv = Dejavu(config)

	local_downloaded_foler = "mp3_downloaded"
	pre_download_all_files_from_s3(local_downloaded_foler)

	# Fingerprint all the mp3's in the directory we give it
	djv.fingerprint_directory(local_downloaded_foler, [".mp3"])