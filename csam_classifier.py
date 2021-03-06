# -*- coding: utf-8 -*-

!pip install nudenet
!pip install py-agender
!pip install hmtai
!pip install wget
!pip3 install tensorflow==1.10
from nudenet import NudeClassifier
from pyagender import PyAgender
import hmtai
import urllib.request
import wget
import tensorflow as tf
import keras
import cv2
import os

# classifies an image and finds the minimum age of all people present in the image
def age_class(filename):
  agender = PyAgender() 
  faces = agender.detect_genders_ages(cv2.imread(filename))
  min_age = 200
  for face in faces:
    curr_age = face['age']
    min_age = min(curr_age, min_age)
  print("The minimum age found was: " + str(min_age))
  return min_age

# classifies an image to contain nudity with a specific probability betwee 0 and 1
def nude_class(filename):
  classifier = NudeClassifier()
  nude_results = classifier.classify(filename)
  nude_prob = nude_results[filename]['unsafe']
  print("The probability that nudity is present in this image is: " + str(nude_prob))
  return nude_results[filename]['unsafe']

# determines whether an image is considered CSAM, return True if CSAM and False otherwise
def is_csam(url):
  filename = wget.download(url)
  age = age_class(filename)
  nude_prob = nude_class(filename)  
  csam = nude_prob > 0.8 and age < 18
  os.remove(filename)
  return csam

def eval_im(self, message):
  output = (0, 0)
  if message.attachments.size > 0:
    image_url = message.attachments.first().url
    if is_csam(image_url):
      # do report flow thing
      output[0] = 1
