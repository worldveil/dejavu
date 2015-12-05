import os
from flask import Flask, request, redirect, url_for
from flask import send_file
from dejavu import Dejavu
from dejavu.recognize import FileRecognizer
from flask import jsonify

app = Flask(__name__)

UPLOAD_FOLDER = ''
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

def init():
	config = {
		 "database": {
			"host": "127.0.0.1",
			"user": "root",
			"passwd": "root", 
			"db": "dejavu",
		 }
	 }
	djv = Dejavu(config)
	return djv


def deleteFile(file_name):
	if os.path.exists(file_name):
		os.remove(file_name)

def getFile(file_name="hello.wav"):
	if request.method == 'POST':
		print "Got Request"
		file = request.files['file']
		file.save(file_name)
		return file_name
	else:
		# send error
		pass

# @app.route('/', methods=['GET','POST'])
# def hello():
# 	if request.method == 'POST':
# 		print "Got Request"
# 		file = request.files['file']
# 		file.save('hello.wav')
# 		init(mp3_file = 'hello.wav')
# 		return send_file('hello.png', mimetype='image/png')
# 	else:
# 		return "Get World"

@app.route('/recognize', methods=['POST'])
def recognize():
	song_name = getFile()
	djv = init()
	song = djv.recognize(FileRecognizer,song_name)
	print song
	deleteFile(song_name)
	# if song["confidence"] < 3000:
	# 	song = {
	# 			"confidence": 0,
	# 			"file_sha1": song["file_sha1"],
	# 			"match_time": song["match_time"],
	# 			"offset": 0,
	# 			"offset_seconds": 0,
	# 			"song_id": 0,
	# 			"song_name": "Not found"
	# 			}
	# else:
		# resp = jsonify(song)
	resp = jsonify(song)
	resp.status_code = 200
	return resp


@app.route('/fingerprint', methods=['POST'])
def fingerprint():
	song_name = getFile()
	djv = init()
	djv.fingerprint_file(song_name)
	deleteFile(song_name)



if __name__ == "__main__":
	# app.run()
	port = int(os.environ.get('PORT', 5000))
	app.run(host='127.0.0.1', port=port)
