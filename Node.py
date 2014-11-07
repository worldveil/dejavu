class Node:
"""
class Node:
Node is a class representing a song match node in a list.
Used in conjunction with KMaxList.py

ATTRIBUTES
  songID - song identification number for the mysql database
  count  - Number of hit - Tied to confidence
  diff   - Offset of the hit
  nextNode - next node in the list
  previous - previous node in the list - unused - TODO

METHODS
  __init__(self,songID,count,diff) : Constructor

  -------- sets/gets ----------
  setNext()
  setPrevious()
  getPrevious()
  getNext()
  getSongID()
  getDiff()
  getCount()
  -----------------------------

  printNode : print the songID,count,diff of the node.
"""

  def __init__(self,songID,count,diff):
    self.songID = songID
    self.count = count
    self.diff = diff
    self.nextNode = None
    self.previous = None

  def setNext(self,nextNode):
    self.nextNode = nextNode
  def setPrevious(self,previousNode):
    self.previousNode = previousNode

  def getPrevious(self):
    return self.previous
  def getNext(self):
    return self.nextNode
  def getCount(self):
    return self.count
  def getDiff(self):
    return self.diff
  def getSongID(self):
    return self.songID
  def printNode(self):
    print "SongID : %d , Count : %.1f , diff : %.3f" %(self.songID,self.count,self.diff)
