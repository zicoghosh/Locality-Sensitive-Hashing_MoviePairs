# -*- coding: utf-8 -*-
"""Implementing LSH in PySpark

Automatically generated by Colaboratory.

# Locality Sensitive Hashing

Here we implement localitiy sensitive hashing step-by-step and apply that on detecting almost duplicate names. You are required to implement the functions as instructed. Do not change the signatures of the functions.

## Setup environment

We need to setup pyspark and pydrive.
"""

!pip install pyspark
!pip install -U -q PyDrive
!pip install mmh3
!apt install openjdk-8-jdk-headless -qq
import os
import itertools
os.environ["JAVA_HOME"] = "/usr/lib/jvm/java-8-openjdk-amd64"

"""Follow the interactive instructions for accessing the file in Google drive."""

from pydrive.auth import GoogleAuth
from pydrive.drive import GoogleDrive
from google.colab import auth
from oauth2client.client import GoogleCredentials

# Authenticate and create the PyDrive client
auth.authenticate_user()
gauth = GoogleAuth()
gauth.credentials = GoogleCredentials.get_application_default()
drive = GoogleDrive(gauth)

"""### Load the appropriate file

The files are shared on Google drive, with the following ids given. Choose to keep the appropriate line, use the corresponding filename and comment the others. After executing, you should be able to see the file in the files section on the left panel.
"""

# id='1aoZykfz5GLGGw3lRA86ogd7yCsgkgHoT' # for titles-small.txt
id='1IPssUa3m-zfWmvVbLtI-lKhJbeZjIgBg' # for titles-10k.txt (with 10k titles, mid sized file)
# id='1RzTA4iOfH3bOiyG2kDaxweUuj4AEcMda' # for titles.txt (7 million+ titles)
downloaded = drive.CreateFile({'id': id})
downloaded.GetContentFile('titles-10k.txt')

"""## Parameters

Let us set our parameters. You are free to change these around and experiment.
"""

# Number of hash functions
n = 32
# size of each shingle
k = 5
# num of bands
b = 8

"""### 1. Converting a string to shingles (of characters)

In our setup, the items we would compare are movie titles (strings). You would have to convert names to sets of k-shingles (of characters), <i>after removing the whitespaces</i> and <i>converting to lowercase</i>. For example, the 3-shingling of the name <tt>'Die hard'</tt> would be <tt>['die', 'ieh', 'eha', 'har', 'ard']</tt>.

Implement the following function which takes a string and k as input and outputs the list of unique shingles generated from the string.
"""

def string_to_shingles(name, k):
    name = name.replace(" ","")
    name = name.lower()
    shingles= []
    for i in range(len(name)-k+1):
      shingles.append(name[i:i+k])
    return shingles

"""Also test your code."""

# print(string_to_shingles('DIe hArd',3))

"""### 2. Generating the shingle - item matrix from the whole data

For each title, first give it an ID. You can do it by the <tt>zipWithIndex()</tt> operation on Spark RDDs. Try testing it first. 

Then, for each title, get the list of shingles in map and for each unique shingle, get the list of IDs using reduce. 

Tips: when your input RDD is a list of tuples of the following form:

<tt>
    [('Die hard', 0),
 ('Die another day', 1),
 ('Tomorrow never dies', 2),
 ('Chup ke chup ke', 3), .... ]
</tt>

for each tuple <tt>t</tt>, you may use <tt>t[0], t[1]</tt> etc to access the first, second (and so on) elements of the tuples.
"""

from pyspark import SparkContext, SparkConf
sc = SparkContext.getOrCreate()

# Use appropriate file path here
titles = sc.textFile("/content/titles-10k.txt")

# Get the number of titles
N = titles.count()
print("Number of titles: %d"%N)

from collections.abc import Iterable
import re

def apply_to_items(name):
  name_shingles = string_to_shingles(name[0], k)
  return_list = []

  for item in name_shingles:
    return_list.append((item,name[1]))

  return (return_list)


def to_list(a):
    return [a]

def append(a, b):
    if (b not in a):
      a.append(b)
    return a

def extend(a, b):
    a.extend(b)
    return a


itemsByShingles = titles.zipWithIndex() # Implement the rest

keyVal = itemsByShingles.flatMap(apply_to_items)

shingle_ids_list = keyVal.combineByKey(to_list, append, extend)

"""Your output should look like 

list of (shingle, [list of movie ids])
"""

# print("Shingle ids list (10 sample):\n")
# print(shingle_ids_list.takeSample(False,100))
# shingle_ids_list.takeSample(False,100)

# Get the number of shingles
m = shingle_ids_list.count()
print("No of Shingles: %d "% m)

# temp_list = shingle_ids_list.takeSample(False,30)

# print("Sample of 20 shingles and id list:\n")
# for item in temp_list:
#   print(item)
# del temp_list

"""### 3. Computation of min-hash signature matrix

Instead of using random permutations, you will implement min-hash function using Murmurhash (v3) functions, as discussed in the class. The input to your function should be a <i>title</i> (which corresponds to a row) and the output should be a number (hash value). 

Recall the outline of the min-hash signature matrix algorithm:<br><br>

<tt>
1. For each row $r$ BEGIN<br>
2. &emsp;Compute $h_1(r), h_2(r),???, h_n(r)$<br>
3. &emsp;  For each column $j$ BEGIN <br>
4. &emsp; &emsp;  If the $j$-th column has 1 in row $r$ <br>
5. &emsp;&emsp;&emsp; For each $i = 1, 2, ??? , n$ BEGIN <br>
6. &emsp;&emsp;&emsp;&emsp; set $\mathrm{SIG}_{i,j} = \min(\mathrm{SIG}_{i,j}, h_i(r))$<br>
7. &emsp;&emsp;&emsp;            END <br>
8. &emsp;&emsp;        END IF<br>
9. &emsp;  END<br>
10. END
</tt>

For each shingle, we have the list of movie IDs which contain the shingle. So, for each shingle (each row), we can perform the actions in lines 5-7 only for the movie IDs that are present in the list. For any other $j$, the $j$-th column does not have a 1 in row $r$.

Do not create a SIG matrix and try to update it. Instead, note that for every 1-entry in the shingle-id matrix (that is, every id in the list corresponding to a shingle), the corresponding (i, id)-th entry of the signature matrix may get potentially updated. Simply output the tuple ((i, id), h_i(text)) in another map. The final value of the (i,id)-th entry of the signature matrix is the minimum of all such h_i(text) values obtained in this process. That minimum can be computed by another reduce process. 

### (a) The map
To make it easier, you may implement an <tt>update_signature</tt> function which takes the shingle (text), the list of ids associated with the shingle and the total number of ids (for computing the hash values). It should simply return the tules <tt>((i, id), h_i(text))</tt> for all i = 1, ..., n.
"""

# Implement the rest here
import mmh3

def update_signature(text, ids, N):
    
    # n: hyperparameter already set before as no of hash functions to use
    h = [mmh3.hash(text,i) % N for i in range(n)]
    
    min_sig = []

    for id in ids:
      for i in range(n):
        min_sig.append(((i,id),h[i]))
    
    return (min_sig)

# update_signature('HisBe', [2], m)

"""### (b) The reduce

Now that you have all <tt>((i, id), h_i(shingle))</tt> tuples output by the map, use reduce to compute the minimum of <tt>h_i(shingle)</tt> for every <tt>(i,id)</tt> key. This would produce the signature matrix in a sparse matrix representation. 

You may actually implement the map function above and call map and reduce together later as well.
"""

# signature = # Implement the rest here

# You should use map with the update_signature function and a reduce 

def map2(tup):
  shingle = tup[0]
  ids = tup[1]
  N =m   #m = count of shingles 
  return update_signature(shingle, ids, N)

keyVal2 = shingle_ids_list.flatMap(map2)

signature = keyVal2.reduceByKey(lambda a, b: min(a,b))

# signature.take(5)
# keyVal2.takeSample(False,20)
# signature.take(False,20)

print("signature matrix (20 samples)")
# print(signature.take(20))
# signature.take(500)

"""The RDD signature should be of the following form:

<tt>
    [((0, 1), 5), ((0, 3), 56), ... 
    ]
</tt>

where each tuple <tt>((i,j),v)</tt> represents the $(i,j)$-th entry of the signature matrix with value $v$.

### 4. Implement the banding

Now configure your number of bands $b$ (a divisor of number of hash functions $n$) and implement the candidate pair computation for a similarity threshold $s$. Any pair of movies which agree completely in their signature on at least one band should be output as candidate pairs.
"""

candidate_pairs = []

# b = 4
a = int(n/b)
hash_to_band = {}

#dictionary stores the hash_fn to band mapping
band_idx = 0

for i in range(a,n+1,a):
  j = band_idx * a
  while ( j < i):
    hash_to_band[j] = band_idx
    j+=1
  band_idx +=1


"""
map3: takes the signature function as input, and maps each (hash_fn,id):val  to (band, id):val, in this way, if
      e.g. there is 2 hash funcs in one band, like hash_fns#:1,2 belong to band#:1 and id:4 has value 45,37 for the hash funcs resp,
      we get (1,4):45 and (1,4):37 as key val pair in the mapped rdd
"""

def map3(tup):

  hash_fn = tup[0][0]
  id = tup[0][1]
  val = tup[1]
  b = hash_to_band[hash_fn]
  return ((b, id), val)

  
def to_list(a):
    return [a]

def append(a, b):
    if (b not in a):
      a.append(b)
    return a

def extend(a, b):
    a.extend(b)
    return a

keyVal3 = signature.map(map3)

"""
band_id_valuelist:
When we combinebyKey the mapped rdd, we get (band, id):[value1,value2,....valuen] if there are n hash funcs in each band
"""

band_id_valuelist = keyVal3.combineByKey(to_list, append,extend)
#band_id_valuelist.takeSample(False, 10)

"""
map4: return (band_no, value_seq) : id as the key value pair, so id's which match in all the rows of a band 
      will have the same value_seq. hence when we combine all keys we get list of ids which are a candidate pair,
       because they have matched completely for a particular band 
"""

def map4(tup):
  value_seq = tuple(tup[1])
  band = tup[0][0]
  id = tup[0][1]

  return ((band, value_seq), id)


keyVal4 = band_id_valuelist.map(map4)
band_complete_matchList = keyVal4.combineByKey(to_list, append, extend)
# band_complete_matchList.takeSample(False,10)


"""
band_complete_matchList has many (band, value_seq): list(ids) such that list length is one, they give no matching pari,
hence we discard them, we only take list having length >1
"""
cand_pair_rdd = band_complete_matchList.filter(lambda x: len(x[1])>1)
# cand_pair_rdd.takeSample(False,10)

"""
cand_pair_lol : is list of list e.g. [[id1,id2,id3],[id5,id6],......[id45,id23,id667,id123]]
"""
cand_pair_lol = cand_pair_rdd.map(lambda x: x[1])
# cand_pair_lol.takeSample(False,10)


"""
make pair from all the list of list which we have
"""
def makePairs(lis):
  return list(itertools.combinations(lis, 2))

candidates = cand_pair_lol.flatMap(makePairs)
# candidates.take(17)

def map_split(tup):
  index = tup[1]
  id1 = tup[0][0]
  id2 = tup[0][1]
  ret_list = []
  ret_list.append((id1, index))
  ret_list.append((id2,index))
  
  return ret_list

"""
giving index to each candidate pair:
"""
candidates_index = candidates.zipWithIndex()
# candidates_index.take(5)

"""
create a flat map, of key:val = id, index so for id1 and id2 having index idx i.e (id1,id2):idx,
we get (id1,idx) and (id2,idx) as key value pairs
"""
candidates_split = candidates_index.flatMap(map_split)
# candidates_split.take(5)

def rev_kv(tup):
  return (tup[1],tup[0])

"""
basically making the items:id key value reverse to id:item, here item is the movie name 
"""
itemsByShingles_rev=itemsByShingles.map(rev_kv)
# itemsByShingles_rev.take(20)

"""
joining by movie id, and get the movie candidate pairs
"""
def to_list_fn(a):
    return [a]

def append_fn(a, b):
    if (b not in a):
      a.append(b)
    return a

def extend_fn(a, b):
    a.extend(b)
    return a

"""
doing join with id names and just extracting the pairs in required output format
"""
join1 = candidates_split.join(itemsByShingles_rev)
join2= join1.map(lambda x: (x[1][0], x[1][1])).combineByKey(to_list_fn, append_fn, extend_fn)
candidate_pairs_raw = join2.filter(lambda x: len(x[1])>1).map(lambda b: tuple(b[1]))

candidate_pairs = candidate_pairs_raw.filter(lambda x: x[0]!=x[1])

print("Candidate Pairs:\n")
# candidate_pairs.takeSample(False,20)

"""The candidate pairs should be of the form

<tt>
    [(movie1, movie2), (movie1, movie2), ... ]
</tt>
    
Optionally, you may also want to compute the pairwise actual Jaccard similarities for each candidate pair and test the number of false positives and negatives.

#Jacard Similarity#
"""

# candidates_local = candidates.collect()

# def Jacard_similarity(tup):
#   id1 = tup[0]
#   id2 = tup[1]

#   hash_list1 = [None]*n

#   sig_id1 = signature.filter(lambda x: x[0][1] == id1).map(lambda x: (x[0][0], x[1])).collect()
#   sig_id2 = signature.filter(lambda x: x[0][1] == id2).map(lambda x: (x[0][0], x[1])).collect()

#   for item1 in sig_id1:
#     hash_list1[item1[0]]=item1[1]
  
#   count=0
#   for item2 in sig_id2:
#     if (hash_list1[item2[0]] == item2[1]):
#       count+=1
  
#   return count/n

# avg = 0
# min = float('inf')
# sum=0

# for pair in candidates_local:
#   # print(pair)
#   sim = Jacard_similarity(pair)
#   sum+=sim
#   if (sim< min):
#     min=sim

# avg = sum/len(candidates_local)


# print("Avg Jacard similarity of candidate pairs:",avg)
# print("Min Jacard similarity of candidate pairs:",min)