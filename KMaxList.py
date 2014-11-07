import Node
class KMaxList:
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
  def __init__(self,first,maxElement):
    self.first = first
    self.minValue = first.getCount()
    self.maxElement = maxElement
    self.length = 1
  def __init__(self,maxElement):
    self.first = None
    self.minValue = None
    self.maxElement = maxElement
    self.length = 0
  def add(self,newNode):
    if self.first is None:
      self.first = newNode
      self.minValue = newNode.getCount()
      self.length += 1
      return
    n = self.first
    if (self.length < self.maxElement):
        while n.getNext() is not None:
              n = n.getNext()

        n.setNext(newNode)
        newNode.setPrevious = n
        self.length += 1
        if self.minValue > newNode.getCount():
          self.minValue = newNode.getCount()
    else:
      if newNode.getCount() <= self.minValue:
        return
      else:
        while n.getNext() is not None:
          if n.getNext().getCount() == self.minValue:
            newNode.setNext(n.getNext().getNext())
            n.setNext(newNode)
            break
          n = n.getNext()
        self.resetMinValue()

  def getMinValue(self):
    return self.minValue
  def printList(self):
    n = self.first
    while n is not None:
       n.printNode()
       n = n.getNext()

  def resetMinValue(self):
    node = self.first
    self.minValue = node.getCount
    while node is not None:
      if self.minValue > node.getCount():
        self.minValue = node.getCount()
      node = node.getNext()


  def getFirst(self):
    return self.first
