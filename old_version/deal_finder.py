import argparse
import sys

def estimate_market_value(sold_prices):
    if not sold_prices:
        raise ValueError("sold_prices must contain at least one value")
    return sum(sold_prices) / len(sold_prices)


def find_deal(current_price, sold_prices, discount=0.7):
    market_value = estimate_market_value(sold_prices)
    threshold = market_value * discount
    is_deal = current_price < threshold
    return is_deal, market_value, threshold


def parse_sold_prices(s):
    try:
        return [float(x) for x in s.split(",") if x.strip() != ""]
    except ValueError:
        raise argparse.ArgumentTypeError("Sold prices must be comma-separated numbers")


def main():
    parser = argparse.ArgumentParser(description="Simple deal finder for auctions")
    parser.add_argument("--price", "-p", type=float, help="Current auction price")
    parser.add_argument("--sold", "-s", type=parse_sold_prices,
                        help="Comma-separated recent sold prices (e.g. 210,225,230)")
    parser.add_argument("--discount", "-d", type=float, default=0.7,
                        help="Fraction of market value considered a deal (default 0.7)")
    args = parser.parse_args()

    sold_prices = args.sold or [210, 225, 230, 240, 235]

    if args.price is None:
        try:
            args.price = float(input("Enter current auction price: "))
        except (ValueError, EOFError):
            print("Invalid price input", file=sys.stderr)
            sys.exit(1)

    try:
        is_deal, market_value, threshold = find_deal(args.price, sold_prices, args.discount)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)

    print(f"Market Value: {market_value:.2f}")
    print(f"Buy Under:    {threshold:.2f} (discount {args.discount:.2f})")
    print(f"Current Price:{args.price:.2f}")
    print("GOOD DEAL" if is_deal else "PASS")


if __name__ == "__main__":
    main()