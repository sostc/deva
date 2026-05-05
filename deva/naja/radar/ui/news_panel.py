"""Radar UI — 新闻 SSE 客户端"""

from pywebio.output import put_html


def _news_stream_client_js() -> str:
    """生成新闻 SSE 客户端 JS"""
    return '''
(function() {
    console.log('[News] 新闻流 JS 执行');

    var minImportance = 0.0;

    window.NajaNewsStream = (function() {
        var listeners = [];
        var source = null;

        function connect() {
            if (source) return;
            console.log('[News] 连接 SSE...');
            source = new EventSource('/api/news/stream?min_importance=' + minImportance);

            source.onopen = function() {
                console.log('[News] SSE 连接已打开');
            };

            source.onmessage = function(event) {
                console.log('[News] onmessage 触发');
                try {
                    var data = JSON.parse(event.data);
                    console.log('[News] 收到数据:', data);
                    listeners.slice().forEach(function(listener) {
                        try {
                            listener(data);
                        } catch (e) {
                            console.error('[News] listener 失败:', e);
                        }
                    });
                } catch (e) {
                    console.error('[News] 解析失败:', e);
                }
            };

            source.onerror = function(error) {
                console.error('[News] SSE 错误:', error);
            };
        }

        return {
            subscribe: function(listener) {
                listeners.push(listener);
                connect();
                return function() {
                    var index = listeners.indexOf(listener);
                    if (index >= 0) listeners.splice(index, 1);
                };
            },
            setMinImportance: function(val) {
                minImportance = val;
                console.log('[News] 设置筛选阈值:', val);
            }
        };
    })();

    window.setNewsMinImportance = function(val) {
        if (window.NajaNewsStream) {
            window.NajaNewsStream.setMinImportance(val);
        }
    };
})();
'''


def init_news_stream():
    """初始化新闻 SSE 客户端（供其他组件调用）"""
    put_html(f"<script>{_news_stream_client_js()}</script>")
