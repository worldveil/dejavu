# Clear out previous results
rm -rf ./results ./temp_audio

python run_tests.py \
	--secs 5 \
	--temp ./temp_audio \
	--log-file ./results/dejavu-test.log \
	--padding 8 \
	--seed 42 \
	--results ./results \
	./mp3
