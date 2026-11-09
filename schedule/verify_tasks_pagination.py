"""Exercise snapshots against paged DOM fixtures using a real headless browser."""
import json
from pathlib import Path
import tempfile
from unittest.mock import patch
from tasks_browser import TasksBrowser, UnsupportedTasksPage, TemporaryTasksPage, synchronize
from tasks_core import TaskStore
from playwright.sync_api import sync_playwright


def row(index,done):
    return (f'<div role="listitem" data-id="{index}"><span data-aria-label="Task title" '
            f'data-rendered-value="Lesson {index}"></span><button aria-label="Mark completed: Lesson" '
            f'aria-pressed="{str(done).lower()}"></button>'
            '<div role="button" aria-label="Scheduled for Nov 6, 2026"></div></div>')


with sync_playwright() as driver:
    browser=driver.chromium.launch(channel='msedge',headless=True)
    page=browser.new_page();reader=TasksBrowser(page)
    page.set_content('<section data-task-list-id="fixture" data-num-completed="11"><h2>My Tasks</h2>'
        +row(0,False)+''.join(row(i,True) for i in range(1,11))+
        '<button aria-label="Load more tasks" id="more">Load more tasks</button></section>')
    page.evaluate('''html=>document.querySelector('#more').onclick=event=>{
        const button=event.currentTarget;button.disabled=true;
        setTimeout(()=>{button.insertAdjacentHTML('beforebegin',html);button.remove()},150)
    }''',row(11,True))
    tasks,lists=reader.snapshot()
    assert len(tasks)==12 and sum(t['completed'] for t in tasks)==11
    assert lists==['fixture'] and len({t['remote_id'] for t in tasks})==12
    # Missing completed rows still must not become an authoritative deletion.
    page.locator('[data-id="11"]').evaluate('(e)=>e.remove()')
    with patch.object(reader,'ready') as reload:
        try:reader.snapshot()
        except TemporaryTasksPage as error:assert str(error)=='completed_rows_incomplete'
        else:raise AssertionError('Partial snapshot was accepted')
        assert reload.call_count==1
    # A disappearing load button cannot conceal an incomplete row count.
    page.locator('section').evaluate("e=>e.setAttribute('data-num-completed','10')")
    tasks,_=reader.snapshot();assert len(tasks)==11
    # Slow asynchronous insertion must recover without a reload or a user click.
    page.locator('section').evaluate("e=>e.setAttribute('data-num-completed','11')")
    page.evaluate("html=>setTimeout(()=>document.querySelector('section').insertAdjacentHTML('beforeend',html),900)",row(11,True))
    with patch.object(reader,'ready') as reload:
        tasks,_=reader.snapshot();assert len(tasks)==12
        reload.assert_not_called()
    # Repeated pages may replace the load button and disable it while loading.
    page.set_content('<section data-task-list-id="fixture" data-num-completed="35"><h2>My Tasks</h2>'
        +row(0,False)+''.join(row(i,True) for i in range(1,11))+
        '<button aria-label="Load more tasks">Load more tasks</button></section>')
    page.evaluate('''rows=>{
        let loaded=10;window.batches=0;
        const wire=button=>button.onclick=()=>{
            button.disabled=true;
            setTimeout(()=>{
                const end=Math.min(loaded+10,35);window.batches++;
                for(let i=loaded;i<end;i++)button.insertAdjacentHTML('beforebegin',rows[i-10]);
                loaded=end;
                if(loaded===35)button.remove();
                else{const next=button.cloneNode(true);next.disabled=false;button.replaceWith(next);wire(next)}
            },120)
        };wire(document.querySelector('button[aria-label="Load more tasks"]'))
    }''',[row(i,True) for i in range(11,36)])
    tasks,_=reader.snapshot()
    assert len(tasks)==36 and page.evaluate('window.batches')==3
    # A stale page recovers after the one bounded reload.
    page.locator('[data-id="35"]').evaluate('(e)=>e.remove()')
    with patch.object(reader,'ready',side_effect=lambda:page.locator('section').evaluate(
            "(e,html)=>e.insertAdjacentHTML('beforeend',html)",row(35,True))) as reload:
        tasks,_=reader.snapshot();assert len(tasks)==36 and reload.call_count==1
    # If retries fail, preserve both cached tasks and their unsent completion.
    page.locator('[data-id="35"]').evaluate('(e)=>e.remove()')
    with tempfile.TemporaryDirectory() as folder:
        store=TaskStore(Path(folder)/'tasks.sqlite3')
        store.merge([dict(remote_id='0',list_id='fixture',list_title='My Tasks',
                          title='Lesson 0',due='2026-11-06',completed=False)],['fixture'])
        store.toggle(store.items()[0].id);before=store.items()
        with patch('tasks_browser.TaskStore',return_value=store),patch.object(TasksBrowser,'ready'),patch('tasks_browser.state'):
            try:synchronize(page)
            except TemporaryTasksPage:pass
            else:raise AssertionError('Incomplete list accepted during sync')
        assert store.items()==before and store.items()[0].pending=='status'
    browser.close()
print(json.dumps(dict(paged_completed_loaded=True,incomplete_snapshot_rejected=True,
    slow_page_recovers=True,multiple_pages=True,reload_recovers=True,pending_edits_preserved=True)))
