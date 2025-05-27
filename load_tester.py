import requests
import time
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed

def send_request(url: str) -> bool:
    """
    Sends a single GET request to the specified URL and returns True on success (200 OK),
    False otherwise. Handles common request exceptions.
    """
    try:
        response = requests.get(url, timeout=30)  # 30-second timeout for gallery requests
        if response.status_code == 200:
            return True
        else:
            # Optionally, log or print more details about non-200 responses
            # print(f"Request to {url} failed with status code {response.status_code}")
            return False
    except requests.exceptions.Timeout:
        # print(f"Request to {url} timed out.")
        return False
    except requests.exceptions.ConnectionError:
        # print(f"Request to {url} failed due to connection error.")
        return False
    except requests.exceptions.RequestException as e:
        # Catch any other request-related errors
        # print(f"An error occurred while requesting {url}: {e}")
        return False

def main():
    """
    Main function to parse arguments, run the load test, and print results.
    """
    parser = argparse.ArgumentParser(description="COMP5349 AWS Load Testing Script")
    parser.add_argument(
        "--url",
        type=str,
        required=True,
        help="Target URL for the load test (e.g., ALB DNS name)."
    )
    parser.add_argument(
        "-n", "--num-requests",
        type=int,
        default=1000,
        help="Total number of requests to send (default: 1000)."
    )
    parser.add_argument(
        "-c", "--concurrency",
        type=int,
        default=10,
        help="Number of concurrent threads (simulated users) (default: 10)."
    )
    args = parser.parse_args()

    if args.num_requests <= 0:
        print("Error: Number of requests must be positive.")
        return
    if args.concurrency <= 0:
        print("Error: Concurrency must be positive.")
        return
    
    # Validate URL format (basic check)
    if not (args.url.startswith("http://") or args.url.startswith("https://")):
        print(f"Warning: URL '{args.url}' does not start with http:// or https://. Proceeding anyway.")


    print("Starting load test...")
    print(f"Target URL: {args.url}")
    print(f"Total Requests: {args.num_requests}")
    print(f"Concurrency Level: {args.concurrency}")
    print("-" * 30)

    start_time = time.time()
    successful_requests = 0
    failed_requests = 0
    
    # Calculate progress reporting interval, ensuring it's at least 1
    # and reports at most 10 times (for 10%, 20%, ..., 100%)
    # or for every request if total requests are less than 10.
    progress_interval = max(1, args.num_requests // 10)
    if args.num_requests < 10:
        progress_interval = 1


    with ThreadPoolExecutor(max_workers=args.concurrency) as executor:
        futures = [executor.submit(send_request, args.url) for _ in range(args.num_requests)]

        for i, future in enumerate(as_completed(futures)):
            if future.result():
                successful_requests += 1
            else:
                failed_requests += 1
            
            # Progress reporting
            if (i + 1) % progress_interval == 0 or (i + 1) == args.num_requests:
                current_progress = ((i + 1) / args.num_requests) * 100
                print(f"Progress: {current_progress:.0f}% ({i + 1}/{args.num_requests} requests completed)")

    end_time = time.time()
    total_time = end_time - start_time
    rps = successful_requests / total_time if total_time > 0 else 0

    print("\n" + "=" * 30)
    print("Load Test Summary")
    print("=" * 30)
    print(f"Total Requests Sent: {args.num_requests}")
    print(f"Concurrency Level:   {args.concurrency}")
    print(f"Successful Requests: {successful_requests}")
    print(f"Failed Requests:     {failed_requests}")
    print(f"Total Test Duration: {total_time:.2f} seconds")
    print(f"Requests Per Second (RPS): {rps:.2f}")
    print("=" * 30)

if __name__ == "__main__":
    main() 