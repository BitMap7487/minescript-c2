import minescript
import time

def run(stop_event):
    minescript.echo("⛏️ Mining loop active...")
    
    # Check each iteration if we need to stop
    while not stop_event.is_set():
        minescript.player_press_attack(True)
            
        # Wait in small steps so we respond immediately to stop
        # instead of waiting 0.6s if stop was just pressed
        if stop_event.wait(0.6):
            minescript.player_press_attack(False)
            break

    minescript.echo("⛏️ Mining closed.")
