# src/core/autoKeywords_GovDeals.py


# Dump trucks
DUMP_PHRASES = {
    "dump truck", "dump bed", "dump-body", "dump body",
    "single axle dump", "tandem dump",
}

# Bucket trucks
BUCKET_PHRASES = {
    "bucket truck", "boom truck", "aerial lift", "cherry picker", "manlift",
     "platform lift",
}
BUCKET_BRANDS = {
    "altec", "terex", "hi-ranger", "versalift", "dur-a-lift", "lift-all",
    "at37", "at37g", "at-37", "at200", "at235",
}

# Crane trucks
CRANE_PHRASES = {
    "crane truck", "truck mounted crane", "service crane", "boom crane",
    "knuckleboom", "digger derrick", "derrick digger",
}
CRANE_BRANDS = {
    "manitex", "stellar", "auto crane", "elliott", "palfinger", "national crane",
}

# Box trucks
BOX_PHRASES = {
    "box truck", "straight truck", "van body", "cargo box",
}

# Emergency
EMERGENCY_PHRASES = {
    "ambulance", "rescue truck", "fire truck", "pumper",
}

# Utility / refuse / tanker
UTILITY_REFUSE_TANKER_PHRASES = {
    "utility line truck", "line truck", "mechanic body",
      
     "roll off", "roll-off",
    "tanker truck", "vactor", "sewer truck",
    "cement mixer", "mixer truck", "liftgate", "tommy gate",
    "knapheide", "reading body",
}

# Heavy-duty chassis / models
HEAVY_DUTY_MODELS = {
    "f450", "f-450", "f550", "f-550", "f650", "f-650", "f750", "f-750", "super duty",
    "ram 4500", "ram 5500",
    "topkick", "kodiak", "c4500", "c5500", "c6500", "gmc 6500",
    "chevy 4500", "chevy 5500",
    "durastar", "workstar",
    "freightliner m2", "m2 106", "m2-106", "sterling",
    "isuzu npr", "isuzu nqr", "hino", "peterbilt", "kenworth",
}

# Diesel / engine keywords
DIESEL_KWS = {
    "diesel", "turbo diesel", "power stroke", "powerstroke", "duramax", "cummins",
    "caterpillar", "cat c7", "cat c9", "dt466", "maxxforce", "t444e", "om906", "mbe900",
    "6.7l", "7.3l", "5.9l", "8.3l", "7.2l",
}
CUMMINS_KWS = {
    "cummins", "isx", "b5.9", "5.9l",
    "6.7 cummins", "6.7l cummins",
}

# Super tight strong flip trucks mode 

STRONGER_FLIPS = {
   # Bucket / aerial / boom
    "bucket truck", "boom truck", "aerial lift", "cherry picker", "manlift", "platform lift",
    "altec", "terex", "versalift", "dur-a-lift", "lift-all",
    "at37", "at37g", "at-37", "at200", "at235",
    "hi-ranger", "hi ranger",

    # Dump trucks
    "dump truck", "dump bed", "dump-body", "dump body",
    "single axle dump", "tandem dump",

    # Mechanics / service / crane trucks
    "service truck", "utility truck", "mechanics truck", "service body", "mechanic body",
    "knapheide", "reading body",
    "crane truck", "truck mounted crane", "service crane", "boom crane",
    "knuckleboom", "digger derrick", "derrick digger",
    "stellar", "imt", "auto crane", "palfinger", "elliott", "national crane",

    # Heavy chassis
    "f450", "f-450", "f550", "f-550", "f650", "f-650", "f750", "f-750",
    "ram 4500", "ram 5500",
    "freightliner m2", "m2 106", "m2-106",
    "international 4300", "4300",
    "durastar", "workstar", "sterling", "topkick", "kodiak"
}

# All keywords that make it a "target truck" if seen anywhere in the text
#-------TARGET_KEYWORDS = set().union(
    #--DUMP_PHRASES,
    #--BUCKET_PHRASES,
    #--BUCKET_BRANDS,
    #--CRANE_PHRASES,
    #--CRANE_BRANDS,
    #--BOX_PHRASES,
    #--EMERGENCY_PHRASES,
    #--UTILITY_REFUSE_TANKER_PHRASES,
    #--HEAVY_DUTY_MODELS,
    #--DIESEL_KWS,
    #--CUMMINS_KWS,
#---------)

#Manual mode for stronger flips only if i want to switch back its commmented out above and comment this out if i want to switch back 
TARGET_KEYWORDS = STRONGER_FLIPS

EXCLUDE_KEYWORDS = {
    "bus", "school bus", "transit bus", "shuttle", "coach", "passenger",
    "garbage truck", "rv", "motorhome",
    "sweeper", "forklift", "tractor",
    "chassis only", "cab and chassis", "parts only", "salvage"
}


# -------------------------------
# States allowed for alerting
# -------------------------------
ALERT_STATES = [
    "Texas",
    "Arkansas",
    "Oklahoma",
    "Louisiana",
    "Mississippi",
    "Alabama",
    "Georgia",
    "Florida",
]
