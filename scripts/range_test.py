import time
import math 

start = time.time()
# this is a huge effing number
n = 2 ** 200 +1
start = time.time()
for i in range(3, n, 2):
    if n % i == 0:
        print(i) # this is so much better and cleaner than printf("%d\n", i)
end = time.time()
print(f"Executed in: {end-start}") 

# correct implementation because we can't have factors 
# larger than sqrt(n)

start = time.time()
for i in range(3, int(math.sqrt(n)) + 1, 2):
    if n % i == 0:
        print(i)
end = time.time()
print(f"Executed in: {end-start}") # this is so much faster
# # exactly as in C, BASIC and any older language
# # but why would I write something like this?
# i = 3
# while i < n:
#     if n % i == 0:
#         print(i)
#     i += 2
end = time.time()
print(f"Executed in: {end-start}") 
