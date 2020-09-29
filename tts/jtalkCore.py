# jtalkCore.py
# -*- coding: utf-8 -*-
# Copyright (C) 2013-2019 Takuya Nishimoto

from __future__ import absolute_import

import re
import os
import sys
if sys.version_info.major >= 3:
	xrange = range
	encode_mbcs = lambda s : s
else:
	encode_mbcs = lambda s : s.encode('mbcs')
try:
	from .mecab import *
except (ImportError, ValueError):
	from tts.mecab import *

c_char_p_p = POINTER(c_char_p) 

############################################

class NJDNode(Structure):
	pass
class NJD(Structure):
	_fields_ = [
		("head", POINTER(NJDNode)),
		("tail", POINTER(NJDNode)),
		]
NJD_ptr = POINTER(NJD)

############################################

class JPCommonNode(Structure):
	pass
JPCommonNode_ptr = POINTER(JPCommonNode)
JPCommonNode._fields_ = [
		('pron', c_char_p),
		('pos', c_char_p),
		('ctype', c_char_p),
		('cform', c_char_p),
		('acc', c_int),
		('chain_flag', c_int),
		('prev', JPCommonNode_ptr),
		('next', JPCommonNode_ptr),
		]

class JPCommonLabelBreathGroup(Structure):
	pass
JPCommonLabelBreathGroup_ptr = POINTER(JPCommonLabelBreathGroup)

class JPCommonLabelAccentPhrase(Structure):
	pass
JPCommonLabelAccentPhrase_ptr = POINTER(JPCommonLabelAccentPhrase)

class JPCommonLabelWord(Structure):
	pass
JPCommonLabelWord_ptr = POINTER(JPCommonLabelWord)

class JPCommonLabelMora(Structure):
	pass
JPCommonLabelMora_ptr = POINTER(JPCommonLabelMora)

class JPCommonLabelPhoneme(Structure):
	pass
JPCommonLabelPhoneme_ptr = POINTER(JPCommonLabelPhoneme)

# jpcommon/jpcommon.h
class JPCommonLabel(Structure):
	_fields_ = [
		('size', c_int),
		('feature', c_char_p_p),
		('breath_head', JPCommonLabelBreathGroup_ptr),
		('breath_tail', JPCommonLabelBreathGroup_ptr),
		('accent_head', JPCommonLabelAccentPhrase_ptr),
		('accent_tail', JPCommonLabelAccentPhrase_ptr),
		('word_head', JPCommonLabelWord_ptr),
		('word_tail', JPCommonLabelWord_ptr),
		('mora_head', JPCommonLabelMora_ptr),
		('mora_tail', JPCommonLabelMora_ptr),
		('phoneme_head', JPCommonLabelPhoneme_ptr),
		('phoneme_tail', JPCommonLabelPhoneme_ptr),
		('short_pause_flag', c_int),
		]
JPCommonLabel_ptr = POINTER(JPCommonLabel)

class JPCommon(Structure):
	_fields_ = [
		("head", JPCommonNode_ptr),
		("tail", JPCommonNode_ptr),
		("label", JPCommonLabel_ptr),
		]
JPCommon_ptr = POINTER(JPCommon)

#############################################

FNLEN = 1000
FILENAME = c_char * FNLEN
FILENAME_ptr = POINTER(FILENAME)
FILENAME_ptr_ptr = POINTER(FILENAME_ptr)

libjt = None
njd = NJD()
jpcommon = JPCommon()

#def libjt_version():
#	if libjt is None: return "libjt version none"
#	return libjt.jt_version()

def libjt_initialize(JT_DLL):
	global libjt, njd, jpcommon
	
	if libjt is None: libjt = cdll.LoadLibrary(encode_mbcs(JT_DLL))
	#libjt.jt_version.restype = c_char_p

	# argtypes & restype
	
	libjt.NJD_initialize.argtypes = [NJD_ptr]
	libjt.NJD_refresh.argtypes = [NJD_ptr]
	libjt.NJD_clear.argtypes = [NJD_ptr]
	libjt.mecab2njd.argtypes = [NJD_ptr, FEATURE_ptr_array_ptr, c_int]
	libjt.njd_set_pronunciation.argtypes = [NJD_ptr]
	libjt.njd_set_digit.argtypes = [NJD_ptr]
	libjt.njd_set_accent_phrase.argtypes = [NJD_ptr]
	libjt.njd_set_accent_type.argtypes = [NJD_ptr]
	libjt.njd_set_unvoiced_vowel.argtypes = [NJD_ptr]
	libjt.njd_set_long_vowel.argtypes = [NJD_ptr]
	libjt.njd2jpcommon.argtypes = [JPCommon_ptr, NJD_ptr]

	libjt.JPCommon_initialize.argtypes = [JPCommon_ptr]
	libjt.JPCommon_clear.argtypes = [JPCommon_ptr]
	libjt.JPCommon_refresh.argtypes = [JPCommon_ptr]
	libjt.JPCommon_make_label.argtypes = [JPCommon_ptr]
	libjt.JPCommon_get_label_size.argtypes = [JPCommon_ptr]
	libjt.JPCommon_get_label_size.argtypes = [JPCommon_ptr]
	libjt.JPCommon_get_label_feature.argtypes = [JPCommon_ptr]
	libjt.JPCommon_get_label_feature.restype = c_char_p_p
	libjt.JPCommon_get_label_size.argtypes = [JPCommon_ptr]

	# initialize

	libjt.NJD_initialize(njd)
	libjt.JPCommon_initialize(jpcommon)

def libjt_refresh():
	libjt.JPCommon_refresh(jpcommon)
	libjt.NJD_refresh(njd)

def libjt_clear():
	libjt.NJD_clear(njd)
	libjt.JPCommon_clear(jpcommon)

def g2p(feature,
		size,
		join=True):
	if feature is None or size is None: return None
	libjt.mecab2njd(njd, feature, size)
	libjt.njd_set_pronunciation(njd)
	libjt.njd_set_digit(njd)
	libjt.njd_set_accent_phrase(njd)
	libjt.njd_set_accent_type(njd)
	libjt.njd_set_unvoiced_vowel(njd)
	libjt.njd_set_long_vowel(njd)
	libjt.njd2jpcommon(jpcommon, njd)
	libjt.JPCommon_make_label(jpcommon)

	s = libjt.JPCommon_get_label_size(jpcommon)
	if s > 2:
		f = libjt.JPCommon_get_label_feature(jpcommon)
		labels = []
		for i in range(s):
			# This will create a copy of c string
			# http://cython.readthedocs.io/en/latest/src/tutorial/strings.html
			#labels.append(<unicode>label_feature[i])
			labels.append(f[i].decode(os.environ['JTALK_ENCODE']))
		prons = list(map(lambda s: s.split("-")[1].split("+")[0], labels[1:-1]))
		if join:
			prons = " ".join(prons)
		libjt_refresh()
		return prons
	libjt_refresh()
	return []
