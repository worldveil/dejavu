# To run:
#   export HACK_S3_BUCKET=ken-hack

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
	import botocore
	client = boto3.client('s3')

	HACK_S3_BUCKET = os.environ('HACK_S3_BUCKET')

	paginator = client.get_paginator('list_objects_v2')
	result = paginator.paginate(Bucket=HACK_S3_BUCKET, StartAfter='2018')

	if not os.path.exists(local_downloaded_foler):
		print("Creating local directory...{}".format(local_downloaded_foler))
		os.makedirs(local_downloaded_foler)

	for page in result:
		if "Contents" in page:
			for key in page["Contents"]:
				keyString = key["Key"]
				try:
					client.Bucket(HACK_S3_BUCKET).download_file(keyString, local_downloaded_foler + "/" + keyString)
				except botocore.exceptions.ClientError as e:
					if e.response['Error']['Code'] == "404":
						print("The object does not exist.")
					else:
						print("failed....")


if __name__ == '__main__':

	# create a Dejavu instance
	djv = Dejavu(config)

	local_downloaded_foler = "mp3_downloaded"
	pre_download_all_files_from_s3(local_downloaded_foler)

	# Fingerprint all the mp3's in the directory we give it
	djv.fingerprint_directory(local_downloaded_foler, [".mp3"])