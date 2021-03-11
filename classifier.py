from nudenet import NudeClassifier
from pyagender import PyAgender
import hmtai

classifier = NudeClassifier()



def nude_class(filename):
	nude_results = classifier.classify(filename)
	return nude_results[filename]['unsafe']

def age_class(filename):
	agender = PyAgender() 
	# see available options in __init__() src
	faces = agender.detect_genders_ages(cv2.imread(filename))
	# [
	#   {left: 34, top: 11, right: 122, bottom: 232, width:(r-l), height: (b-t), gender: 0.67, age: 23.5},
	#   ...
	# ]
	min_age = 200
	for face in faces:
		curr_age = face['age']
		min_age = min(curr_age, min_age)
	return min_age


def is_csam(filename):
	return nude_class(filename) > 0.8 and age_class(filename) < 18

def main():
	filename = "nude_ex.jpeg'"
	print(is_csam(filename))
	# loop over files in folder
