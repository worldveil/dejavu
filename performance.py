from dejavu.control import Dejavu
from dejavu.recognize import Recognizer
from dejavu.convert import Converter
from dejavu.database import SQLDatabase
from ConfigParser import ConfigParser
from scipy.io import wavfile
import matplotlib.pyplot as plt
import warnings
import pyaudio
import os, wave, sys
import random
import numpy as np
warnings.filterwarnings("ignore")

config = ConfigParser()
config.read("dejavu.cnf")
dejavu = Dejavu(config)
recognizer = Recognizer(dejavu.fingerprinter, config)

def test_recording_lengths(recognizer):
    
    # settings for run
    RATE = 44100
    FORMAT = pyaudio.paInt16
    padding_seconds = 10
    SONG_PADDING = RATE * padding_seconds
    OUTPUT_FILE = "output.wav"
    p = pyaudio.PyAudio()
    c = Converter()
    files = c.find_files("va_us_top_40/wav/", [".wav"])[-25:]
    total = len(files)
    recording_lengths = [4]
    correct = 0
    count = 0
    score = {}
    
    for r in recording_lengths:
        
        RECORD_LENGTH = RATE * r
        
        for tup in files:
            f, ext = tup 
            
            # read the file
            #print "reading: %s" % f
            Fs, frames = wavfile.read(f)
            wave_object = wave.open(f)
            nchannels, sampwidth, framerate, num_frames, comptype, compname = wave_object.getparams()
            
            # chose at random a segment of audio to play
            possible_end = num_frames - SONG_PADDING - RECORD_LENGTH
            possible_start = SONG_PADDING
            if possible_end - possible_start < RECORD_LENGTH:
                print "ERROR! Song is too short to sample based on padding and recording seconds preferences."
                sys.exit()
            start = random.randint(possible_start, possible_end)
            end = start + RECORD_LENGTH + 1
            
            # get that segment of samples
            channels = []
            frames = frames[start:end, :]
            wav_string = frames.tostring()
            
            # write to disk
            wf = wave.open(OUTPUT_FILE, 'wb')
            wf.setnchannels(nchannels)
            wf.setsampwidth(p.get_sample_size(FORMAT))
            wf.setframerate(RATE)
            wf.writeframes(b''.join(wav_string))
            wf.close()
            
            # play and test
            correctname = os.path.basename(f).replace(".wav", "").replace("_", " ")
            inp = raw_input("Click ENTER when playing %s ..." % OUTPUT_FILE)
            song = recognizer.listen(seconds=r+1, verbose=False)
            print "PREDICTED: %s" % song['song_name']
            print "ACTUAL: %s" % correctname
            if song['song_name'] == correctname:
                correct += 1
            count += 1
                
            print "Currently %d correct out of %d in total of %d" % (correct, count, total)
            
        score[r] = (correct, total)
        print "UPDATE AFTER %d TRIAL: %s" % (r, score)
    
    return score
            
def plot_match_time_trials():
    
    # I did this manually
    t = np.array([1, 2, 3, 4, 5, 6, 7, 8, 10, 15, 25, 30, 45, 60])
    m = np.array([.47, .79, 1.1, 1.5, 1.8, 2.18, 2.62, 2.8, 3.65, 5.29, 8.92, 10.63, 16.09, 22.29])
    mplust = t + m
    
    # linear regression
    A = np.matrix([t, np.ones(len(t))])
    print A
    w = np.linalg.lstsq(A.T, mplust)[0]
    line = w[0] * t + w[1]
    print "Equation for line is %f * record_time + %f = time_to_match" % (w[0], w[1])
    
    # and plot
    plt.title("Recording vs Matching time for \"Get Lucky\" by Daft Punk")
    plt.xlabel("Time recorded (s)")
    plt.ylabel("Time recorded + time to match (s)")
    #plt.scatter(t, mplust)
    plt.plot(t, line, 'r-', t, mplust, 'o')
    plt.show()
    
def plot_accuracy():
    # also did this manually
    secs = np.array([1, 2, 3, 4, 5, 6])
    correct = np.array([27.0, 43.0, 44.0, 44.0, 45.0, 45.0]) 
    total = 45.0
    correct = correct / total
    
    plt.title("Dejavu Recognition Accuracy as a Function of Time")
    plt.xlabel("Time recorded (s)")
    plt.ylabel("Accuracy")
    plt.plot(secs, correct)
    plt.ylim([0.0, 1.05])
    plt.show()
    
def plot_hashes_per_song():
    squery = """select song_name, count(song_id) as num 
    from fingerprints 
    natural join songs
    group by song_name 
    order by count(song_id) asc;"""
    sql = SQLDatabase(username="root", password="root", database="dejavu", hostname="localhost")
    cursor = sql.connection.cursor()
    cursor.execute(squery)
    counts = cursor.fetchall()
    
    songs = []
    count = []
    for item in counts:
        songs.append(item['song_name'].replace("_", " ")[4:])
        count.append(item['num'])
    
    pos = np.arange(len(songs)) + 0.5
    
    fig = plt.figure()
    ax = fig.add_subplot(111)
    ax.barh(pos, count, align='center')
    ax.set_yticks(pos, tuple(songs))
    
    ax.axvline(0, color='k', lw=3)
    
    ax.set_xlabel('Number of Fingerprints')
    ax.set_title('Number of Fingerprints by Song')
    ax.grid(True)
    plt.show()
    
#plot_accuracy()       
#score = test_recording_lengths(recognizer)
#plot_match_time_trials() 
#plot_hashes_per_song() 
