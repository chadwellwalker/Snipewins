from datetime import datetime

end_time_text = input("Enter auction end time (YYYY-MM-DD HH:MM:SS): ")
end_time = datetime.strptime(end_time_text, "%Y-%m-%d %H:%M:%S")

now = datetime.now()
seconds_left = (end_time - now).total_seconds()

if seconds_left <= 0:
    print("Auction already ended.")
else:
    minutes = int(seconds_left // 60)
    seconds = int(seconds_left % 60)
    print(f"Time left: {minutes} minutes, {seconds} seconds")