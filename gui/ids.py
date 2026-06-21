# Component ID constants — single source of truth for layout + callbacks.

SEND_BTN            = "send-btn"
STOP_BTN            = "stop-btn"               # cancels the running server-side turn
COMPOSER            = "composer"
MESSAGES_SCROLL     = "messages-scroll"
STREAM_MESSAGE      = "stream-message"        # live-updating bubble during generation
THREAD_LIST         = "thread-list"
THREAD_ID_STORE     = "thread-id-store"       # dcc.Store: current thread id (str)
THREADS_DATA_STORE  = "threads-data-store"    # dcc.Store: list of thread metadata
MESSAGES_STORE      = "messages-store"        # dcc.Store: list of rendered message dicts
THEME_STORE         = "theme-store"           # dcc.Store: "dark" | "light"
NEW_CHAT_BTN        = "new-chat-btn"
PENDING_SEND        = "pending-send"          # dcc.Store: queued outgoing message {text, ts}
THEME_TOGGLE        = "theme-toggle"
UPLOAD              = "upload"
UPLOAD_STORE        = "upload-store"          # dcc.Store: last uploaded file info
TITLE_EDIT          = "title-edit"
WELCOME_SCREEN      = "welcome-screen"
LOADING_INDICATOR   = "loading-indicator"
INIT_INTERVAL       = "init-interval"
GRAPH_THEME_DUMMY   = "graph-theme-dummy"     # dummy output for graph re-theming callback
