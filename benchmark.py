import time
from aic.session import Session
import os

def run_benchmark():
    session = Session({})
    # Create 1000 dummy files with more content
    for i in range(1000):
        with open(f"dummy_{i}.txt", "w") as f:
            f.write(f"content of dummy file {i}\n" * 10)
        session.add_context_file(f"dummy_{i}.txt")

    start_time = time.time()
    for _ in range(100):
        session.get_messages()
    end_time = time.time()

    print(f"Time taken to get_messages 100 times with 1000 context files: {end_time - start_time:.4f} seconds")

    # Cleanup
    for i in range(1000):
        os.remove(f"dummy_{i}.txt")

if __name__ == "__main__":
    run_benchmark()
