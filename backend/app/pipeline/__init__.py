"""Job kind -> handler. Queues (and what runs where):

  fetch        fetch.source, fetch.item      network (connectors, article pages)
  parse        parse.item                    normalize, language, SHA-256 dedupe
  filter       filter.item                   rules, SimHash, embedding + cluster
  ai_fast      ai.classify                   topic / relevance / sentiment
  ai_deep      ai.summarize                  bullets / takeaway / keywords
  deliver      deliver.fanout, deliver.send  Web Push
  maintenance  maint.*                       reaper, hotness, cleanup, reconcile, trends,
                                             youtube_stats
"""

from app.pipeline import ai, deliver, fetch, maintenance, parse_filter

HANDLERS = {
    "fetch.source": fetch.handle_fetch_source,
    "fetch.item": fetch.handle_fetch_item,
    "parse.item": parse_filter.handle_parse_item,
    "filter.item": parse_filter.handle_filter_item,
    "ai.classify": ai.handle_classify,
    "ai.summarize": ai.handle_summarize,
    "deliver.fanout": deliver.handle_fanout,
    "deliver.send": deliver.handle_send,
    "maint.reap": maintenance.handle_reap,
    "maint.hotness": maintenance.handle_hotness,
    "maint.cleanup": maintenance.handle_cleanup,
    "maint.reconcile": maintenance.handle_reconcile,
    "maint.trends": maintenance.handle_trends,
    "maint.youtube_stats": maintenance.handle_youtube_stats,
    "maint.local_classifier_eval": maintenance.handle_local_classifier_eval,
}
