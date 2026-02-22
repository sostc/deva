"""Context builders for admin route wrappers."""


SSE_LOG_JS = r'''
// 确保DOM元素存在
function ensureElementReady(selector, callback) {
    const checkExist = setInterval(function() {
        const element = document.querySelector(selector);
        if (element) {
            clearInterval(checkExist);
            callback(element);
        }
    }, 100);
}
if (window.sseConnection) { window.sseConnection.close(); }
window.sseConnection = new EventSource('/logsse');
ensureElementReady('#webio-logbox-log', function(messageList) {
    window.sseConnection.onopen = function() { console.log('SSE连接已打开，等待消息...'); };
    window.sseConnection.onmessage = function(event) {
        try {
            const data = JSON.parse(event.data);
            const message = data.message || data;
            const logbox = document.querySelector("#webio-logbox-log");
            if (logbox) {
                const logEntry = `${new Date().toLocaleTimeString()} - ${message}\n`;
                logbox.textContent += logEntry;
                logbox.scrollTop = logbox.scrollHeight;
            } else {
                console.warn('未找到logbox元素');
            }
            messageList.scrollTop = messageList.scrollHeight;
        } catch (error) {
            console.error('处理SSE消息时出错:', error);
        }
    };
});
window.sseConnection.onerror = function(error) {
    console.error('SSE连接出错:', error);
    if (window.sseConnection) { window.sseConnection.close(); }
    setTimeout(() => {
        try {
            window.sseConnection = new EventSource('/logsse');
            console.log('SSE连接已重新建立');
        } catch (e) {
            console.error('重新连接SSE失败:', e);
        }
    }, 5000);
};
console.log('SSE脚本已加载');
console.log('当前页面URL:', window.location.href);
console.log('SSE连接URL:', '/logsse');
'''


def tasks_ctx(ns):
    return {
        'NB': ns['NB'],
        'tasks': ns['tasks'],
        'scheduler': ns['scheduler'],
        'log': ns['log'],
        'toast': ns['toast'],
        'run_js': ns['run_js'],
        'input_group': ns['input_group'],
        'input': ns['input'],
        'textarea': ns['textarea'],
        'select': ns['select'],
        'TEXT': ns['TEXT'],
        'async_gpt': ns['async_gpt'],
        'get_gpt_response': ns['get_gpt_response'],
        'use_scope': ns['use_scope'],
        'put_text': ns['put_text'],
        'put_table': ns['put_table'],
        'put_button': ns['put_button'],
        'put_row': ns['put_row'],
        'put_collapse': ns['put_collapse'],
        'stop_task': ns['stop_task'],
        'start_task': ns['start_task'],
        'delete_task': ns['delete_task'],
        'recover_task': ns['recover_task'],
        'remove_task_forever': ns['remove_task_forever'],
        'manage_tasks': ns['manage_tasks'],
        'global_ns': ns,
    }


def document_ui_ctx(ns):
    return {
        'cache': ns['_DOCUMENT_CACHE'],
        'cache_ttl': ns['_DOCUMENT_CACHE_TTL'],
        'warn': ns['warn'],
        'put_text': ns['put_text'],
        'put_button': ns['put_button'],
        'put_table': ns['put_table'],
        'put_row': ns['put_row'],
        'put_tabs': ns['put_tabs'],
        'run_async': ns['run_async'],
        'inspect_object': ns['inspect_object'],
        'run_object_smoke_test': ns['_run_object_smoke_test'],
        'document': ns['document'],
        'popup': ns['popup'],
        'put_markdown': ns['put_markdown'],
        'put_html': ns['put_html'],
        'extract_doc_examples': ns['_extract_doc_examples'],
        'mask_attr_value': ns['_mask_attr_value'],
    }


def tables_ctx(ns, admin_tables):
    return {
        'NB': ns['NB'],
        'ls': ns['ls'],
        'sample': ns['sample'],
        'pd': ns['pd'],
        'pin': ns['pin'],
        'clear': ns['clear'],
        'warn': ns['warn'],
        'toast': ns['toast'],
        'popup': ns['popup'],
        'close_popup': ns['close_popup'],
        'input_group': ns['input_group'],
        'input': ns['input'],
        'textarea': ns['textarea'],
        'put_markdown': ns['put_markdown'],
        'put_row': ns['put_row'],
        'put_table': ns['put_table'],
        'put_text': ns['put_text'],
        'put_button': ns['put_button'],
        'put_buttons': ns['put_buttons'],
        'put_collapse': ns['put_collapse'],
        'put_datatable': ns['put_datatable'],
        'put_file_upload': ns['put_file_upload'],
        'put_input': ns['put_input'],
        'use_scope': ns['use_scope'],
        'run_async': ns['run_async'],
        'traceback': ns['traceback'],
        'log': ns['log'],
        'datetime': ns['datetime'],
        'table_click': ns['table_click'],
        'delete_table': ns['delete_table'],
        'create_new_table': ns['create_new_table'],
        'refresh_table_display': ns['refresh_table_display'],
    }


def main_ui_ctx(ns, admin_tables):
    return {
        'NB': ns['NB'],
        'browser': ns['browser'],
        'tabs': ns['tabs'],
        'tab': ns['tab'],
        'first': ns['first'],
        'Stream': ns['Stream'],
        'timer': ns['timer'],
        'NS': ns['NS'],
        'log': ns['log'],
        'ls': ns['ls'],
        'print': ns['print'],
        'Dtalk': ns['Dtalk'],
        'pin': ns['pin'],
        'asyncio': ns['asyncio'],
        'requests': ns['requests'],
        'json': ns['json'],
        'TEXT': ns['TEXT'],
        'actions': ns['actions'],
        'input': ns['input'],
        'input_group': ns['input_group'],
        'run_js': ns['run_js'],
        'run_async': ns['run_async'],
        'run_asyncio_coroutine': ns['run_asyncio_coroutine'],
        'get_session_implement': ns['get_session_implement'],
        'set_env': ns['set_env'],
        'setup_admin_runtime': ns['setup_admin_runtime'],
        'basic_auth': ns['basic_auth'],
        'get_gpt_response': ns['get_gpt_response'],
        'put_out': ns['put_out'],
        'put_link': ns['put_link'],
        'put_text': ns['put_text'],
        'put_markdown': ns['put_markdown'],
        'put_table': ns['put_table'],
        'put_row': ns['put_row'],
        'put_html': ns['put_html'],
        'put_tabs': ns['put_tabs'],
        'put_button': ns['put_button'],
        'put_buttons': ns['put_buttons'],
        'put_collapse': ns['put_collapse'],
        'put_input': ns['put_input'],
        'put_logbox': ns['put_logbox'],
        'logbox_append': ns['logbox_append'],
        'set_scope': ns['set_scope'],
        'use_scope': ns['use_scope'],
        'clear': ns['clear'],
        'popup': ns['popup'],
        'toast': ns['toast'],
        'PASSWORD': ns['PASSWORD'],
        'datetime': ns['datetime'],
        'stable_widget_id': admin_tables.stable_widget_id,
        'edit_data_popup': ns['edit_data_popup'],
        'write_to_log': ns['write_to_log'],
        'show_timer_detail': ns['show_timer_detail'],
        'sse_js': SSE_LOG_JS,
        'init_admin_ui': ns['init_admin_ui'],
        'view_tab': ns['view_tab'],
        'close_tab': ns['close_tab'],
        'open_new_tab': ns['open_new_tab'],
        'show_browser_status': ns['show_browser_status'],
        'dynamic_popup': ns['dynamic_popup'],
        'summarize_tabs': ns['summarize_tabs'],
        'async_json_gpt': ns['async_json_gpt'],
        'extract_important_links': ns['extract_important_links'],
        'truncate': ns['truncate'],
        'set_table_style': ns['set_table_style'],
        'process_tabs': ns['process_tabs'],
        'extended_reading': ns['extended_reading'],
        'close_all_tabs': ns['close_all_tabs'],
        'show_dtalk_archive': ns['show_dtalk_archive'],
        'view_dtalk_message': ns['view_dtalk_message'],
        'delete_dtalk_message': ns['delete_dtalk_message'],
        'clear_all_dtalk_messages': ns['clear_all_dtalk_messages'],
        'init_floating_menu_manager': ns['init_floating_menu_manager'],
        'create_sidebar': ns['create_sidebar'],
        'create_nav_menu': ns['create_nav_menu'],
        'run_ai_in_worker': ns['run_ai_in_worker'],
        'get_bus_runtime_status': ns['get_bus_runtime_status'],
        'get_bus_clients': ns['get_bus_clients'],
        'get_bus_recent_messages': ns['get_bus_recent_messages'],
        'send_bus_message': ns['send_bus_message'],
    }


def stock_ctx(ns):
    return {
        'init_admin_ui': ns['init_admin_ui'],
        'get_stock_config': ns['get_stock_config'],
        'set_stock_config': ns['set_stock_config'],
        'get_stock_basic_meta': ns['get_stock_basic_meta'],
        'refresh_stock_basic_df': ns['refresh_stock_basic_df'],
        'refresh_stock_basic_df_async': ns['refresh_stock_basic_df_async'],
        'put_markdown': ns['put_markdown'],
        'put_text': ns['put_text'],
        'put_table': ns['put_table'],
        'put_row': ns['put_row'],
        'put_button': ns['put_button'],
        'put_html': ns['put_html'],
        'set_scope': ns['set_scope'],
        'use_scope': ns['use_scope'],
        'run_async': ns['run_async'],
        'toast': ns['toast'],
        'NS': ns['NS'],
    }
