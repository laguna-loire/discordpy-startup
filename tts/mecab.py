# coding: UTF-8
# mecab.py for python-jtalk

from __future__ import absolute_import
import os
import MeCab

CODE = os.environ['JTALK_ENCODE']

from ctypes import *
import threading
import sys
if sys.version_info.major >= 3:
	xrange = range
try:
	libc = cdll.msvcrt
except:
	from ctypes.util import find_library
	libc = CDLL(find_library('c'), use_errno = True)

############################################

# http://mecab.sourceforge.net/libmecab.html
# c:/mecab/sdk/mecab.h
MECAB_NOR_NODE = 0
MECAB_UNK_NODE = 1
MECAB_BOS_NODE = 2
MECAB_EOS_NODE = 3

FELEN   = 1000 # string len
FECOUNT = 1000
FEATURE = c_char * FELEN
FEATURE_ptr = POINTER(FEATURE)
FEATURE_ptr_array = FEATURE_ptr * FECOUNT
FEATURE_ptr_array_ptr = POINTER(FEATURE_ptr_array)

mecab = None
lock = threading.Lock()

mc_malloc = libc.malloc
mc_malloc.restype = POINTER(c_ubyte)
mc_calloc = libc.calloc
mc_calloc.restype = POINTER(c_ubyte)
mc_free = libc.free

class NonblockingMecabFeatures(object):
	def __init__(self):
		self.size = 0
		self.feature = FEATURE_ptr_array()
		for i in xrange(0, FECOUNT):
			buf = mc_malloc(FELEN) 
			self.feature[i] = cast(buf, FEATURE_ptr)

	def __del__(self):
		for i in xrange(0, FECOUNT):
			try:
				mc_free(self.feature[i]) 
			except:
				pass

class MecabFeatures(NonblockingMecabFeatures):
	def __init__(self):
		global lock
		lock.acquire()
		super(MecabFeatures, self).__init__()

	def __del__(self):
		global lock
		super(MecabFeatures, self).__del__()
		lock.release()

def Mecab_initialize(dic):
	global mecab
	if mecab is None:
		mecab = MeCab.Tagger('-d ' + dic)

def Mecab_analysis(src, features):
	if not src:
		features.size = 0
		return
	head = mecab.parseToNode(src.decode(CODE))
	if head is None:
		features.size = 0
		return
	features.size = 0

	# make array of features
	node = head
	i = 0
	while node:
		s = node.stat
		if s != MECAB_BOS_NODE and s != MECAB_EOS_NODE:
			c = node.length
			s = node.surface.encode(CODE) + b"," + node.feature.encode(CODE)
			buf = create_string_buffer(s)
			dst_ptr = features.feature[i]
			src_ptr = byref(buf)
			memmove(dst_ptr, src_ptr, len(s)+1)
			i += 1
		node = node.next
		features.size = i
		if i >= FECOUNT:
			return
	return