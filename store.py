# To run:
#   export HACK_S3_BUCKET=ken-hack
#   export HACK_S3_BUCKET=ihr-de-stg-nonprod
#   export HACK_S3_PREFIX=hackday_2019

import warnings
import json
warnings.filterwarnings("ignore")

from dejavu import Dejavu


def download_all_files_from_s3_and_fingerprint(local_downloaded_foler):
	# load config from a JSON file (or anything outputting a python dictionary)
	with open("dejavu.cnf.SAMPLE") as f:
		config = json.load(f)

	# create a Dejavu instance
	djv = Dejavu(config)

	import os
	import boto3
	client = boto3.client('s3')
	HACK_S3_BUCKET = os.environ['HACK_S3_BUCKET']
	HACK_S3_PREFIX = os.environ['HACK_S3_PREFIX']
	paginator = client.get_paginator('list_objects_v2')
	result = paginator.paginate(Bucket=HACK_S3_BUCKET, Prefix=HACK_S3_PREFIX, StartAfter='2018')
	local_downloaded_foler_joined = os.path.join(local_downloaded_foler, HACK_S3_PREFIX)
	if not os.path.exists(local_downloaded_foler_joined):
		print("Creating local directory...{}".format(local_downloaded_foler_joined))
		os.makedirs(local_downloaded_foler_joined)
	s3 = boto3.resource('s3')
	for page in result:
		if "Contents" in page:
			for key in page["Contents"]:
				keyString = key["Key"]
				try:
					print('downloading...{}'.format(local_downloaded_foler + "/" + keyString))
					s3.Bucket(HACK_S3_BUCKET).download_file(keyString, local_downloaded_foler + "/" + keyString)

					# Fingerprint all the mp3's in the directory we give it
					djv.fingerprint_directory(local_downloaded_foler, [".mp3"])

					# delete the file
					os.remove(local_downloaded_foler + "/" + keyString)
					print('deleted download...{}'.format(local_downloaded_foler + "/" + keyString))
				except Exception as e:
					print("failed....{}".format(e))


if __name__ == '__main__':
	download_all_files_from_s3_and_fingerprint("mp3_downloaded")