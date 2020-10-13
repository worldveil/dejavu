#####################################
### Dejavu example testing script ###
#####################################

###########
# Clear out previous results
rm -rf ./results ./temp_audio

###########
# Fingerprint files of extension mp3 in the ./mp3 folder
python dejavu.py -f ./mp3/ mp3

##########
# Run a test suite on the ./mp3 folder by extracting 1, 2, 3, 4, and 5 
# second clips sampled randomly from within each song 8 seconds 
# away from start or end, sampling with random seed = 42, and finally 
# store results in ./results and log to dejavu-test.log
python run_tests.py \
	-sec 5 \
	-temp ./temp_audio \
	-lf ./results/dejavu-test.log \
	-pad 8 \
	-sd 42 \
	-res ./results \
	./mp3
