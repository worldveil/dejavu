from dejavu import fingerprint

def seconds_to_hms(seconds):
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)

    if h > 0:
        return "%d:%02d:%02d" % (h, m, s) 
    elif m > 0 and m < 10:
        return "%01d:%02d" % (m, s)
    elif m > 0:
        return "%02d:%02d" % (m, s)
    elif s > 0 and s < 90:
        return ":%02d" % (s,)
    else:
        return "%i" % (s,)
    
def offsets_to_seconds(offset):
    return round(float(offset) / fingerprint.DEFAULT_FS *
                         fingerprint.DEFAULT_WINDOW_SIZE *
                         fingerprint.DEFAULT_OVERLAP_RATIO, 5)

def seconds_to_offsets(seconds):
    return int(round(float(seconds) * fingerprint.DEFAULT_FS /
                         fingerprint.DEFAULT_WINDOW_SIZE /
                         fingerprint.DEFAULT_OVERLAP_RATIO, 0))

def convert_timecodes(input_dictionary):
    " Takes a dictionary as input and returns a dictionary with times in hh:mm:ss format of strings. "
    output_dictionary = {}

    for key in input_dictionary.copy().keys():
        if (isinstance(input_dictionary[key], float) or isinstance(input_dictionary[key], int)) and input_dictionary[key] > 60:        
            output_dictionary[key] = "{}".format(seconds_to_hms(input_dictionary[key]))
        else:
            output_dictionary[key] = input_dictionary[key]

    return output_dictionary            