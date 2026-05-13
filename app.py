import ebay_tools
from settings_tools import view_settings, edit_settings
from storage import setup_watchlist


def main():
    setup_watchlist()

    while True:
        print("\n===== AUCTION TOOL MENU =====")
        print("1. Search eBay auctions")
        print("2. Search eBay and save to watchlist")
        print("3. Auto deal radar")
        print("4. Live deal radar")
        print("5. Auto import radar")
        print("6. Live auto import radar")
        print("7. Auto import ending-soon radar")
        print("8. Live auto import ending-soon radar")
        print("9. View ending soon watchlist")
        print("10. Sniper queue")
        print("11. Top sniper targets")
        print("12. Sniper alerts")
        print("13. View settings")
        print("14. Edit settings")
        print("15. Exit")

        choice = input("\nChoose an option: ").strip()

        if choice == "1":
            ebay_tools.search_ebay()

        elif choice == "2":
            ebay_tools.search_and_save()

        elif choice == "3":
            ebay_tools.deal_radar()

        elif choice == "4":
            ebay_tools.live_deal_radar()

        elif choice == "5":
            ebay_tools.auto_import_radar()

        elif choice == "6":
            ebay_tools.live_auto_import_radar()

        elif choice == "7":
            ebay_tools.auto_import_ending_soon_radar()

        elif choice == "8":
            ebay_tools.live_auto_import_ending_soon_radar()

        elif choice == "9":
            ebay_tools.view_ending_soon()

        elif choice == "10":
            ebay_tools.sniper_queue()

        elif choice == "11":
            ebay_tools.top_sniper_targets()

        elif choice == "12":
            ebay_tools.sniper_alerts()

        elif choice == "13":
            view_settings()

        elif choice == "14":
            edit_settings()

        elif choice == "15":
            print("Goodbye.")
            break

        else:
            print("Please choose 1 through 15.")


if __name__ == "__main__":
    main()