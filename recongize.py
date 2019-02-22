# To run:
#   export HACK_S3_BUCKET_RECONGIZE=ken-hack-recongize

import warnings
import json
warnings.filterwarnings("ignore")

from dejavu import Dejavu
from dejavu.recognize import FileRecognizer

# load config from a JSON file (or anything outputting a python dictionary)
with open("dejavu.cnf.SAMPLE") as f:
    config = json.load(f)

def download_files(local_downloaded_foler):
	import os
	import boto3
	client = boto3.client('s3')
	HACK_S3_BUCKET_RECONGIZE = os.environ['HACK_S3_BUCKET_RECONGIZE']
	paginator = client.get_paginator('list_objects_v2')
	result = paginator.paginate(Bucket=HACK_S3_BUCKET_RECONGIZE, StartAfter='2018')
	if not os.path.exists(local_downloaded_foler):
		print("Creating local directory...{}".format(local_downloaded_foler))
		os.makedirs(local_downloaded_foler)
	s3 = boto3.resource('s3')
	output = []
	for page in result:
		if "Contents" in page:
			for key in page["Contents"]:
				keyString = key["Key"]
				print('downloading...{}'.format(keyString))
				try:
					s3.Bucket(HACK_S3_BUCKET_RECONGIZE).download_file(keyString, local_downloaded_foler + "/" + keyString)
					output.append(keyString)
				except Exception as e:
					print("failed....{}".format(e))

	return output
if __name__ == '__main__':
	# create a Dejavu instance
	djv = Dejavu(config)

	local_downloaded_foler = "mp3_downloaded_recongize"
	# Recognize audio from a file

	all_songs_to_be_recongized = download_files(local_downloaded_foler)
	for song_name in all_songs_to_be_recongized:
		song = djv.recognize(FileRecognizer, local_downloaded_foler + "/" + song_name)
		print "For song: {}, From file we recognized: {} \n".format(song_name, song)

	# Or recognize audio from your microphone for `secs` seconds
	# secs = 5
	# song = djv.recognize(MicrophoneRecognizer, seconds=secs)
	# if song is None:
	# 	print "Nothing recognized -- did you play the song out loud so your mic could hear it? :)"
	# else:
	# 	print "From mic with %d seconds we recognized: %s\n" % (secs, song)
	#
	# # Or use a recognizer without the shortcut, in anyway you would like
	# recognizer = FileRecognizer(djv)
	# song = recognizer.recognize_file("mp3/Josh-Woodward--I-Want-To-Destroy-Something-Beautiful.mp3")
	# print "No shortcut, we recognized: %s\n" % song