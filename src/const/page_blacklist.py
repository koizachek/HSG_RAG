PAGE_BLACKLIST = [
    'cookie', 'cookies', 'privacy', 'datenschutz', 'popup', 'download',
    'cookie-policy', 'privacy-policy', 'cookie-and-privacy-policy',
    'data-protection', 'impressum', 'legal', 'terms', 'agb', 'imprint',
    'mp4', 'pdf', 'interview', 'why', 'warum', 'treffen-sie-uns', 'meet-us',
    'corona', 'ranking', 'tour', 'besuch', 'visit', 'page_id',
    # The chatbot's own consent/test pages (emba.unisg.ch/chatbot-test,
    # /chatbot-test-consent) were indexed and tagged with all three
    # programmes; in the pilot they surfaced in nearly every retrieval.
    'chatbot',
]
