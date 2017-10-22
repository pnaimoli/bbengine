#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Module docstring"""

import itertools
import xml.etree.ElementTree as ET
import unittest

###############################################################################
# Globals
###############################################################################
#SUITS = {"C": "♣", "D": "♦", "H": "♥", "S": "♠", "N": "NT"}
SUITS = ("S", "H", "D", "C")
RANKS = ("A", "K", "Q", "J", "T", "9", "8", "7", "6", "5", "4", "3", "2", "1")
DIRECTIONS = ("N", "E", "S", "W")
BIDS = [str(a) + b for (a, b) in itertools.product(range(1, 7),
                                                  ("C", "D", "H", "S", "N"))]

###############################################################################
# Helper functions
###############################################################################
def Evaluator(*args):
    """Returns a function that takes a holding as input.  This function
    in turn calculates how many "points" are in your hand as specified by
    *args.

    Examples: Evaluator(4,3,2,1) gives HCP
              Evaluator(2,1) gives "Italian" controls
    """
    def helper(holding):
        points = 0
        for (rank, value) in zip(RANKS, list(args) + [0]*(len(RANKS)-len(args))):
            points += holding.count(rank)*value
        return points
    return helper

HCPEvaluator = Evaluator(4, 3, 2, 1)
ControlEvaluator = Evaluator(2, 1)

def Shape(shape_string):
    """Returns a function that takes a holding as input.  This function in
    turn calculates whether the given hand follows the specified shape in
    shape_string.

    Examples: Shape("5,3,3,2") matches any hand with the 5332 pattern in any
                               order.
              Shape("5,3") matches any hand with exactly 5 of any suit and 3 of
                          any suit.
              Shape("5+,3-") matches any hand with a suit that is 5 or more
                             cards long and another suit that is 3 or fewer.
              Shape("5-6,3,3,1-2") effectively matches 5332 or 6331.
              Shape("5-6,S3,C3,1-2") as above, but exactly 3 clubs and 3 spades.
              Shape("CD5,4,2,2") either clubs or diamonds is a 5 card suit and
                                 the rest of the hand is 422 in any order.
    """
    def helper(holding):
        return True
    return helper

def next_bid(bid):
    return BIDS[BIDS.index(bid) + 1]

###############################################################################
# Criteria
###############################################################################
class CriteriaChecker():
    """A 'Criterion' is a any type of rule used to determine if a bid
    is appropriate.  Common Criterion include shape, hcp, etc...

    All Criteria should have two functions:
    __call__(xml_element, hand, state)
    get_name()

    To register a custom Criterion, simply do:
    CriteriaChecker.add_criteria(MyCriterion)
    """

    criteria = {}

    @classmethod
    def add_criteria(cls, criterion):
        self = cls()
        if criterion.get_name() in self.criteria:
            raise Exception("Criteria '{}' already registered".format(
                            criterion.get_name()))
        self.criteria[criterion.get_name()] = criterion

    @classmethod
    def check(cls, criteria_elements, hand, state, func=all):
        self = cls()
        checker_partial = lambda x: self._check_one(x, hand, state)
        results = map(checker_partial, criteria_elements)
        return func(results)

    @classmethod
    def _check_one(cls, criterion_element, hand, state):
        self = cls()
        criterion = self.criteria[criterion_element.tag]()
        return criterion(criterion_element, hand, state)

class Criterion():
    @classmethod
    def get_name(cls):
        name = cls.__name__
        if not name.endswith("Criterion"):
            raise Exception("Criterion derived classes must be named xxxxxCriterion")
        return name[:-9].lower()

class OpeningCriterion(Criterion):
    @staticmethod
    def __call__(xml_element, hand, state):
        return not state.has_opened()

class ShapeCriterion(Criterion):
    @staticmethod
    def __call__(xml_element, hand, state):
        return Shape(xml_element.text)(hand)

class BalancedCriterion(Criterion):
    @staticmethod
    def __call__(xml_element, hand, state):
        return Shape("4,3,3,3")(hand) or \
               Shape("4,4,3,2")(hand) or \
               Shape("5,3,3,2")(hand)

class HCPCriterion(Criterion):
    @staticmethod
    def __call__(xml_element, hand, state):
        hcp = HCPEvaluator(hand)
        if hcp < int(xml_element.attrib.get("min", 0)):
            return False
        if hcp > int(xml_element.attrib.get("max", 40)):
            return False
        return True

class OrCriterion(Criterion):
    @staticmethod
    def __call__(xml_element, hand, state):
        return CriteriaChecker.check(xml_element.getchildren(), hand, state, any)

CriteriaChecker.add_criteria(OpeningCriterion)
CriteriaChecker.add_criteria(ShapeCriterion)
CriteriaChecker.add_criteria(BalancedCriterion)
CriteriaChecker.add_criteria(HCPCriterion)
CriteriaChecker.add_criteria(OrCriterion)


###############################################################################
# Handoffs
###############################################################################
class HandOffs():
    handoffs = {}

    @classmethod
    def add_handoff(cls, handoff):
        self = cls()
        if handoff.get_name() in self.handoffs:
            raise Exception("HandOff '{}' already registered".format(
                            handoff.get_name()))
        self.handoffs[handoff.get_name()] = handoff

    @classmethod
    def do(cls, handoff_str, hands, state):
        self = cls()
        handoff = self.handoffs[handoff_str.lower()](hands, state)
        handoff.bid()


class HandOff():
    @classmethod
    def get_name(cls):
        name = cls.__name__
        if not name.endswith("HandOff"):
            raise Exception("HandOff derived classes must be named xxxxxHandOff")
        return name[:-7].lower()

class CONFIHandOff(HandOff):
    """CONFI goes through 3 stages:

    1) Deciding if we have 10+ controls.
    2) Finding a suit fit.
    3) If no suit fit, "power" invite via 5NT.
    """
    def __init__(self, hands, state):
        self.hands = hands
        self.state = state

    def bid(self):
        # First opener tells responder how many controls they have by
        # bidding their controls in steps up the line
        opener = self.state.next_to_bid
        current_hand = self.hands[self.state.next_to_bid]
        opener_controls = ControlEvaluator(current_hand)
        expected_minimum = 6
        bid_steps = max(opener_controls - expected_minimum, 0) + 1
        self.state.add_bid(BIDS[BIDS.index(self.state.bids[-2]) + bid_steps])
        self.state.add_bid("P")

        # Next responder checks to see if they have 10+ controls
        current_hand = self.hands[self.state.next_to_bid]
        responder_controls = ControlEvaluator(current_hand)
        opener_controls = max(opener_controls, expected_minimum)
        if responder_controls + opener_controls < 10:
            # Sign off at the cheapest NT contract
            for i in range(BIDS.index(self.state.bids[-2]), len(BIDS)):
                if BIDS[i].endswith("N"):
                    self.state.add_bid(BIDS[i])
                    break
            else:
                raise Exception("No cheapest NT?")
            self.state.all_pass()
            return

        # If so, begin bidding Qxxx+ suits up the line until we have found
        # a fit
        denied_four_cards = [[False, False, False, False], None,
                             [False, False, False, False], None]
        showed_four_cards = [[False, False, False, False], None,
                             [False, False, False, False], None]
        showed_five_cards = [[False, False, False, False], None,
                             [False, False, False, False], None]
        showed_three_cards = [[False, False, False, False], None,
                             [False, False, False, False], None]
        openers_first_rebid = True
        while True:
            # If opener actually has less than the expected minimum of controls,
            # he needs to sign off at the cheapest NT immediately.
            if self.state.next_to_bid == opener and openers_first_rebid:
                openers_first_rebid = False
                current_hand = self.hands[self.state.next_to_bid]
                opener_controls = ControlEvaluator(current_hand)
                if opener_controls < expected_minimum:
                    current_bid = self.state.highest_bid()
                    if current_bid.endswith("N"):
                        self.state.all_pass()
                        return
                    bid = current_bid
                    while not bid.endswith("N"):
                        bid = next_bid(bid)
                    self.state.add_bid(bid)
                    self.state.add_bid("P")

                    # Responder signs off unless he actually has an extra control (rare)
                    current_hand = self.hands[self.state.next_to_bid]
                    responder_controls = ControlEvaluator(current_hand)
                    opener_controls = max(opener_controls, expected_minimum)
                    if responder_controls + opener_controls < 11:
                        self.state.all_pass()
                        return

            # If opener actually has a 6 card minor, just bid it at the 6 level.
            current_hand = self.hands[self.state.next_to_bid]
            if self.state.next_to_bid == opener:
                for i, suit in enumerate(SUITS):
                    if len(str.split(current_hand)[i]) >= 6:
                        # For now, blanket raise to 6 level and end
                        self.state.add_bid("6" + suit)
                        self.state.all_pass()
                        return


            # Check to see if we have a 4-4 fit with partner
            for i, b in enumerate(showed_four_cards[2 - self.state.next_to_bid]):
                if not b:
                    continue
                suit_holding = str.split(current_hand)[i]
                if len(suit_holding) < 4:
                    continue

                # For now, blanket raise to 6 level and end
                self.state.add_bid("6" + SUITS[i])
                self.state.all_pass()
                return

            # Check to see if we have a 5-3 fit with partner
            for i, b in enumerate(showed_five_cards[2 - self.state.next_to_bid]):
                if not b:
                    continue
                suit_holding = str.split(current_hand)[i]
                if len(suit_holding) < 3:
                    continue

                # For now, blanket raise to 6 level and end
                self.state.add_bid("6" + SUITS[i])
                self.state.all_pass()
                return

            # Check to see if we have a 3-5 fit with partner
            for i, b in enumerate(showed_three_cards[2 - self.state.next_to_bid]):
                if not b:
                    continue
                suit_holding = str.split(current_hand)[i]
                if len(suit_holding) < 5:
                    continue

                # For now, blanket raise to 6 level and end
                self.state.add_bid("6" + SUITS[i])
                self.state.all_pass()
                return

            # If we have not found a 4-4 fit yet, keep introducing suits
            current_bid = self.state.highest_bid()
            bid = self.state.highest_bid()
            for i in range(0, 4):
                bid = next_bid(bid)
                if bid.endswith("N"):
                    bid = next_bid(bid)

                # Make sure we're not exploring bids at the 6 level
                if int(bid[0]) >= 6:
                    break

                # Is this suit even 4 cards long?
                suit_index = SUITS.index(bid[-1])
                suit_holding = str.split(current_hand)[suit_index]
                if len(suit_holding) < 4:
                    denied_four_cards[self.state.next_to_bid][suit_index] = True
                    continue

                # Has partner already denied 4 cards in this suit?
                if denied_four_cards[2 - self.state.next_to_bid][suit_index]:
                    continue

                # Have we already shown this suit to our partner?
                if showed_four_cards[self.state.next_to_bid][suit_index]:
                    continue

                # TODO: If we skip bidding 3 suits, can we play it for a
                # 5-card suit since we don't CONFI with 4333?  It's complicated
                # by the fact that G.R. suggests not showing 4-card suits
                # unless they are headed by an honor.

                # Bid it!
                showed_four_cards[self.state.next_to_bid][suit_index] = True
                self.state.add_bid(bid)
                self.state.add_bid("P")
                break

            # Did we make a bid?
            if current_bid != self.state.highest_bid():
                continue

            # Start showing 5 card suits if we've exhausted our 4-4 potential
            bid = self.state.highest_bid()
            for i in range(0, 4):
                bid = next_bid(bid)
                if bid.endswith("N"):
                    bid = next_bid(bid)

                # Make sure we're not exploring bids at the 6 level
                if int(bid[0]) >= 6:
                    break

                # Is this suit even 5 cards long?
                suit_index = SUITS.index(bid[-1])
                suit_holding = str.split(current_hand)[suit_index]
                if len(suit_holding) < 5:
                    continue

                # Have we already shown this suit to our partner?
                if showed_five_cards[self.state.next_to_bid][suit_index]:
                    continue

                # Bid it!
                showed_five_cards[self.state.next_to_bid][suit_index] = True
                self.state.add_bid(bid)
                self.state.add_bid("P")
                break

            # Did we make a bid?
            if current_bid != self.state.highest_bid():
                continue

            # OK, we're not doing so hot here.  Try introducing a 3-card suit
            # and hope partner actually started with 5 of his previously shown
            # suits.  Only do this if it doesn't take us to the next bidding
            # level.
            bid = self.state.highest_bid()
            for i in range(0, 4):
                bid = next_bid(bid)
                if bid.endswith("N"):
                    bid = next_bid(bid)

                # Make sure we're not bidding at the next level
                if int(bid[0]) > int(current_bid[0]):
                    break

                # Make sure we're not exploring bids at the 6 level
                if int(bid[0]) >= 6:
                    break

                # Is this suit even 3 cards long?
                suit_index = SUITS.index(bid[-1])
                suit_holding = str.split(current_hand)[suit_index]
                if len(suit_holding) < 3:
                    continue

                # Have we already shown this suit to our partner?
                if showed_three_cards[self.state.next_to_bid][suit_index]:
                    continue

                # Has partner even promised 4 of this suit?
                if not showed_four_cards[2 - self.state.next_to_bid][suit_index]:
                    continue

                # Bid it!
                showed_three_cards[self.state.next_to_bid][suit_index] = True
                self.state.add_bid(bid)
                self.state.add_bid("P")
                break

            # Did we make a bid?
            if current_bid != self.state.highest_bid():
                continue

            # Signoff time.  If notrump was just bid, pass it out.
            if current_bid.endswith("N"):
                self.state.all_pass()
                return

            # Otherwise, bid the cheapest NT
            bid = current_bid
            while not bid.endswith("N"):
                bid = next_bid(bid)
            self.state.add_bid(bid)
            self.state.add_bid("P")


HandOffs.add_handoff(CONFIHandOff)

###############################################################################
# Internals
###############################################################################
class Auctioneer():
    """The auctioneer keeps track of all bidding information.  This includes
    all previous bids, the information they publicly convey, who is next to
    bid, etc...
    """
    def __init__(self, dealer):
        self.bids = []
        self.dealer = dealer
        self.next_to_bid = DIRECTIONS.index(dealer)

    def add_bid(self, bid):
        if self.completed():
            raise Exception("Auction is already over!")
        self.bids.append(bid)
        self.next_to_bid = (self.next_to_bid + 1) % len(DIRECTIONS)

    def has_opened(self):
        """Returns whether anybody has made a non-pass bid."""
        if not self.bids:
            return False
        return any((b != "P" for b in self.bids))

    def completed(self):
        """The auction is completed if all 4 players initiall pass,
        or there are 3 consecutive passes following an opening bid.
        """
        if not self.has_opened():
            return len(self.bids) == 4
        elif len(self.bids) < 4:
            return False
        else:
            return all((b == "P" for b in self.bids[-3:]))

    def all_pass(self):
        """Completes the auction by forcing all remaining players to pass."""
        while not self.completed():
            self.add_bid("P")

    def highest_bid(self):
        for bid in reversed(self.bids):
            if bid != "P":
                return bid
        return None

    def final_contract(self):
        if not self.completed():
            return None
        return self.highest_bid()

class bidder():
    def __init__(self):
        pass

    def load_system(self, filename):
        self.full_tree = ET.parse(filename)

    def bid(self, north, south):
        # E/W always passes for now
        hands = [north, None, south, None]
        state = Auctioneer("N")
        self.next_bids = self.full_tree

        while True:
            if not self.next_bids:
                # If we've fully traversed our bidding tree, we're done
                state.all_pass()
                break
            for bid in self.next_bids.findall("./bid"):
#                print(bid.attrib["value"] + ": checking...")
                criteria = bid.find("./criteria")
                if not criteria:
                    print(ET.dump(bid))
                    raise Exception("No criteria found!")

                if not CriteriaChecker.check(criteria, hands[state.next_to_bid],
                                             state):
                    continue

#                print(bid.attrib["value"] + ": matched!")
                state.add_bid(bid.attrib["value"])
                # E/W always passes for now
                state.add_bid("P")
                self.next_bids = bid.find("./responses")
                if "handoff" in bid.attrib:
                    HandOffs.do(bid.attrib["handoff"], hands, state)
                break
            else:
                break
#        print(state.bids)
        return state.bids


if __name__ == "__main__":
    pass

###############################################################################
# Begin unit tests
###############################################################################

class ScoringTest(unittest.TestCase): # pylint: disable=missing-docstring
    def test_basics(self): # pylint: disable=missing-docstring
        b = bidder()
        b.load_system("kokish.system")
        auction = b.bid("AQ3 AK3 J2 AQ652", "K9742 J2 QJ65 K3")
        self.assertEqual(auction, ['2N', 'P', '3N', 'P', '4D', 'P', '4N', 'P', 'P', 'P'])
        auction = b.bid("AQ3 AK3 J2 AQ652", "K9742 J2 K865 K3")
        self.assertEqual(auction, ['2N', 'P', '3N', 'P', '4D', 'P', '4S', 'P', '5C', 'P', '5D', 'P', '5S', 'P', '6S', 'P', 'P', 'P'])

        # From "Win With Romex" page 172
        auction = b.bid("KJx KJxx KJ AKJx", "QTxx AQxx Qxx xx")
        self.assertEqual(auction, ['2N', 'P', '3N', 'P', '4C', 'P', '4N', 'P', 'P', 'P'])
        auction = b.bid("AQxx KJxx AJx AJ", "Kx Jxx Kxxx KQxx")
        self.assertEqual(auction, ['2N', 'P', '3N', 'P', '4D', 'P', '5C', 'P', '5N', 'P', 'P', 'P'])
        auction = b.bid("KQJx KQxx KQx Ax", "Axxx ATx Jx Qxxx")
        self.assertEqual(auction, ['2N', 'P', '3N', 'P', '4C', 'P', '4S', 'P', '4N', 'P', 'P', 'P'])
        auction = b.bid("KJxx QJTx AK AKx", "Axx Axxx QTxx Jx")
        self.assertEqual(auction, ['2N', 'P', '3N', 'P', '4D', 'P', '4H', 'P', '6H', 'P', 'P', 'P'])
        auction = b.bid("AKJT QTxx AJT AJ", "Qxxx Ax KQxx xxx")
        self.assertEqual(auction, ['2N', 'P', '3N', 'P', '4D', 'P', '4S', 'P', '6S', 'P', 'P', 'P'])
        auction = b.bid("AJx AKQ Kxx ATxx", "Qxxx xxx Ax KQxx")
        self.assertEqual(auction, ['2N', 'P', '3N', 'P', '4H', 'P', '4S', 'P', '5C', 'P', '6C', 'P', 'P', 'P'])
        auction = b.bid("Kxx AQTxx AKJ KJ", "AQxx Kxx xx Qxxx")
        self.assertEqual(auction, ['2N', 'P', '3N', 'P', '4D', 'P', '4S', 'P', '5H', 'P', '6H', 'P', 'P', 'P'])
        auction = b.bid("AK QJTx KJxx AQx", "Qxx xx AQx KJxxx")
        self.assertEqual(auction, ['2N', 'P', '3N', 'P', '4C', 'P', '4N', 'P', 'P', 'P'])
        auction = b.bid("AQTx Ax QJx AKxx", "Kx Kxx KTxxx JTx")
        self.assertEqual(auction, ['2N', 'P', '3N', 'P', '4D', 'P', '5D', 'P', '5N', 'P', 'P', 'P'])
        auction = b.bid("AJT QJTx AKJ AJx", "Qxxx Ax xx KQxxx")
        self.assertEqual(auction, ['2N', 'P', '3N', 'P', '4D', 'P', '4S', 'P', '4N', 'P', '5C', 'P', '6C', 'P', 'P', 'P'])
        auction = b.bid("QJ QJxx AKQx AQx", "Ax ATxx xx KT9xx")
        self.assertEqual(auction, ['2N', 'P', '3N', 'P', '4C', 'P', '4H', 'P', '4N', 'P', '5C', 'P', '6H', 'P', 'P', 'P'])

    def test_evaluators(self): # pylint: disable=missing-docstring
        holding = "AKxxx AKx AKx QJ"
        self.assertEqual(HCPEvaluator(holding), 24)
        self.assertEqual(ControlEvaluator(holding), 9)
