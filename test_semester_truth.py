import os
import unittest
from unittest.mock import patch
from types import SimpleNamespace
import update_fangtai as app


def semester(label, waitlist=False, terms=None, **extra):
    return dict(label=label, waitlist=waitlist, terms=terms or {}, dates=[],
                flex_start=None, flex_end=None, contract_end=None, flexible=False, **extra)


def room(sems):
    return dict(slug='premium-studio', name='Premium Studio', type='Studio',
                area='30m²', bed='Double', prices={'短租':850, '44周':1035},
                avail_status='limited', avail_count=2, avail_text='2 left at this price',
                date_data={}, date_str='static date', semesters=sems)


def cities(r):
    return {'sydney': {'label':'悉尼', 'properties':{'Broadway':'broadway'},
                       'room_results':{'broadway':[r]}}}


class SemesterTruthTests(unittest.TestCase):
    def test_current_visible_overview_is_separate_and_only_once(self):
        html = ('<div>From $1,035/wk</div><strong>2 LEFT AT THIS PRICE</strong>'
                '<script>99 LEFT AT THIS PRICE</script><!-- 88 LEFT AT THIS PRICE -->'
                '<div hidden>77 LEFT AT THIS PRICE</div><div style="display:none">66 LEFT AT THIS PRICE</div>')
        sems = [semester('Semester 2 2026',True),semester('Semester 1 2027',terms={'44周':1035})]
        with patch.object(app,'fetch_page',return_value=html), patch.object(app,'extract_semester_radios',return_value=[('s2','Semester 2 2026','1','2'),('','Semester 1 2027','1','2')]), patch.object(app,'fetch_semester_movein',side_effect=sems):
            r=app.scrape_room('sydney','broadway','premium-studio',{})
        output=app.build_room_row(r,['44周'])
        self.assertEqual(output.count('2 LEFT AT THIS PRICE'),1)
        self.assertIn('未归属具体学期/租期',output)
        self.assertIn('采集于',output)
        self.assertIn('https://iglu.com.au/rooms/sydney/broadway/premium-studio/',output)
        for count in ['99','88','77','66']:
            self.assertNotIn(count+' LEFT AT THIS PRICE',output)
        self.assertTrue(all(x['count'] is None for x in app.build_compare_data(cities(r))))
        r['stale']=True
        self.assertNotIn('2 LEFT AT THIS PRICE',app.build_room_row(r,['44周']))
        r.pop('stale')
        r['_snapshot_replay']=True
        self.assertNotIn('2 LEFT AT THIS PRICE',app.build_room_row(r,['44周']))

    def test_old_unproven_marketing_is_not_relabelled_as_current_overview(self):
        r=room([semester('Semester 1 2027',terms={'44周':1035})])
        app.apply_semester_truth(r,r['semesters'])
        self.assertNotIn('room-overview',app.build_room_row(r,['44周']))

    def test_waitlist_response_preserves_supplied_terms_and_dates(self):
        response = {'success': True, 'continue': False,
                    'terms':'<input name="lterm" value="44" data-label="44 Weeks" data-price="1035">'}
        with patch.object(app.cffi_req, 'post', return_value=SimpleNamespace(text=app.json.dumps(response))):
            sem = app.fetch_semester_movein('1','2','s2')
        self.assertTrue(sem['waitlist'])
        self.assertEqual(sem['terms'], {'44周':1035})

    def test_malformed_or_failed_semester_response_is_unknown(self):
        for payload in [{'success': True}, {'success':False}, [], {'success':True,'continue':'false'}]:
            with self.subTest(payload=payload), patch.object(app.cffi_req, 'post', return_value=SimpleNamespace(text=app.json.dumps(payload))):
                self.assertIsNone(app.fetch_semester_movein('1','2',''))

    def test_normal_schedule_send_and_queue_paths_remain_enabled(self):
        recipient = dict(id='test', city='sydney', webhook='https://example.invalid/notification',
                         queue_file='unused.json', quiet_start=22, quiet_end=9)
        with patch.dict(os.environ, {'IGLU_DISABLE_NOTIFICATIONS':'0'}), \
             patch.object(app.urllib.request, 'urlopen') as network:
            network.return_value.__enter__.return_value.read.return_value = b'{"errcode":0,"code":200}'
            app._send_now(recipient, 'test')
            app.send_bark('test', 'test')
            self.assertEqual(network.call_count,2)
        with patch.dict(os.environ, {'IGLU_DISABLE_NOTIFICATIONS':'0'}), \
             patch.object(app, '_in_quiet_hours', return_value=True), \
             patch.object(app, '_load_queue', return_value=[]), \
             patch.object(app, '_save_queue') as save:
            app.notify_recipient(recipient,'test')
            self.assertEqual(save.call_args.args[1][0]['text'],'test')

    def test_disabled_notifications_neither_send_nor_touch_queue(self):
        recipient = dict(id='test', city='sydney', webhook='https://example.invalid/notification',
                         queue_file='unused.json', quiet_start=22, quiet_end=9)
        with patch.dict(os.environ, {'IGLU_DISABLE_NOTIFICATIONS':'1'}), \
             patch.object(app, 'RECIPIENTS', [recipient]), \
             patch.object(app.urllib.request, 'urlopen') as network, \
             patch.object(app, '_load_queue', return_value=[]) as load, \
             patch.object(app, '_save_queue') as save:
            app.send_bark('test', 'test')
            app._send_now(recipient, 'test', True)
            app._flush_queue(recipient)
            app.notify_recipient(recipient, 'test')
            app.notify_city('sydney', 'test')
            app.flush_all_recipients()
            self.assertEqual(network.call_count, 0)
            self.assertEqual(load.call_count, 0)
            self.assertEqual(save.call_count, 0)

    def test_unscoped_count_and_static_price_cannot_become_semester_offer(self):
        r = room([semester('Semester 2 2026', True),
                  semester('Semester 1 2027', terms={'44周':1035})])
        app.apply_semester_truth(r, r['semesters'])
        self.assertIsNone(r['avail_count'])
        self.assertEqual(r['prices'], {'44周':1035})
        self.assertEqual(r['avail_status'], 'available')

    def test_every_semester_keeps_its_own_price_and_unknown(self):
        sems = [semester('Semester 2 2026', terms={'短租':850}),
                semester('Semester 1 2027', terms={'44周':1035}),
                semester('Semester 2 2027', None)]
        r = room(sems)
        app.apply_semester_truth(r, sems)
        rows = app.build_compare_data(cities(r))
        self.assertEqual(len(rows), 3)
        self.assertEqual([x['prices'] for x in rows], [{'短租':850}, {'44周':1035}, {}])
        self.assertEqual([x['avail'] for x in rows], ['available','available','unknown'])
        self.assertTrue(all(x['count'] is None for x in rows))
        self.assertEqual(r['semesters'], sems)

    def test_all_failed_is_unknown_not_static_available(self):
        r = room([])
        app.apply_semester_truth(r, [])
        self.assertEqual(r['avail_status'], 'unknown')
        self.assertEqual(r['prices'], {})
        self.assertIsNone(r['avail_count'])

    def test_same_term_in_two_semesters_does_not_collapse_price_or_date(self):
        sems = [semester('Semester 1 2027', terms={'44周':1035}),
                semester('Semester 2 2027', terms={'44周':1100})]
        sems[0]['dates'] = [[2027,1,4]]
        sems[1]['dates'] = [[2027,7,5]]
        r = room(sems)
        app.apply_semester_truth(r,sems)
        rows = app.build_compare_data(cities(r))
        self.assertEqual([x['prices']['44周'] for x in rows],[1035,1100])
        self.assertIn('2027-01-04',rows[0]['date'])
        self.assertNotIn('2027-07-05',rows[0]['date'])
        self.assertIn('2027-07-05',rows[1]['date'])
        self.assertNotIn('2026',app.build_room_row(r,['44周']))

    def test_reapplying_truth_preserves_raw_marketing_for_audit_only(self):
        r = room([semester('Semester 1 2027',terms={'44周':1035})])
        app.apply_semester_truth(r,r['semesters'])
        app.apply_semester_truth(r,r['semesters'])
        self.assertEqual(r['static_evidence']['avail_count'],2)
        self.assertEqual(r['static_evidence']['prices']['短租'],850)
        self.assertIsNone(r['avail_count'])
        self.assertNotIn('850',app.build_room_row(r,['44周','短租']))

    def test_unknown_and_waitlist_never_collapse_into_all_waitlist(self):
        sems = [semester('S2 2026', True), semester('S1 2027', None)]
        r = room(sems)
        app.apply_semester_truth(r, sems)
        self.assertEqual(r['avail_status'], 'unknown')
        self.assertIn('未知', r['date_str'])
        self.assertIn('等位', r['date_str'])

    def test_all_semester_dates_and_terms_render_without_static_fallback(self):
        sems = [semester('Semester 2 2026', True),
                semester('Semester 1 2027', terms={'44周':1035, '短租':850, '40周':None})]
        sems[1]['dates'] = [[2027,1,4],[2027,2,1]]
        r = room(sems)
        app.apply_semester_truth(r, sems)
        html = app.build_room_row(r, ['44周','短租','40周'])
        for text in ['S2 2026','S1 2027','1035','850','未知','学期日期','租期日期未核验']:
            self.assertIn(text, html)
        self.assertNotIn('仅剩2间', html)
        self.assertNotIn('今年无房', html)

    def test_failure_is_retained_by_scraper(self):
        html = '<input id="sem_s2" data-prop="1" data-room="2" data-suffix="s2"><span id="span_s2">Semester 2 2026</span>'
        for failure in [None, ValueError('malformed semester response')]:
            with self.subTest(failure=failure), patch.object(app, 'fetch_page', return_value=html), patch.object(app, 'fetch_semester_movein', return_value=None, side_effect=failure):
                r = app.scrape_room('sydney','broadway','premium-studio',{})
            self.assertEqual(len(r['semesters']),1)
            self.assertEqual(r['semesters'][0]['label'],'Semester 2 2026')
            self.assertIsNone(r['semesters'][0]['waitlist'])
            self.assertEqual(r['avail_status'],'unknown')

    # —— 固定月份起租（官网第二条起租日路径）——
    # 月份按钮原文取自 2026-10-08 线上接口实测（Central Park / Waterloo / Flagstaff / Broadway）
    MONTHS = ('<ul id="move-in-months" class="dates_block" style="display:none;">'
              '<li class="movin-dates" ><a href="javascript:void(0)" class="btn white-orange lterm22 lterm44 btn-rev"'
              ' data-id="" data-6="" data-12="" data-24="" data-22="12/02/2027" data-44="12/02/2027" data-ss=""'
              ' data-22-gender="all" data-44-gender="all" data-22-prebook="pb-false" data-44-prebook="pb-false">February</a></li>'
              '<li class="movin-dates" ><a href="javascript:void(0)" class="btn white-orange lterm22 lterm44 btn-rev"'
              ' data-id="" data-6="" data-12="" data-24="" data-22="11/03/2027" data-44="11/03/2027" data-ss="">March</a></li>'
              '<li class="btn-waitlist"><a href="javascript:void(0)" class="btn white-orange btn-rev"'
              ' data-44="01/12/2026">Waitlist</a></li>'
              '</ul>')

    def test_month_buttons_yield_fixed_start_dates(self):
        dd = app.extract_dates(self.MONTHS)
        self.assertEqual(dd['fixed_starts'],
                         {'22周': [(2027,2,12),(2027,3,11)], '44周': [(2027,2,12),(2027,3,11)]})
        self.assertNotIn((2026,12,1), dd['fixed_starts'].get('44周', []))  # 等位按钮的日期不算

    def test_fixed_start_renders_as_date_when_no_flexible_window(self):
        sems = [semester('Semester 1 2027', terms={'44周':1015, '22周':1075},
                         fixed_starts={'44周':[[2027,2,12]], '22周':[[2027,2,12]]})]
        r = room(sems)
        app.apply_semester_truth(r, sems)
        view = [v for v in app.semester_views(r) if v['avail_status'] == 'available'][0]
        self.assertEqual(app._sem_date_parts(view), ('固定起租', '02/12', True))
        html = app.build_room_row(r, ['44周','22周'])
        self.assertIn('固定起租', html)
        self.assertIn('固定起租 02/12', app._sem_date_short(view))
        self.assertNotIn('官网未给可选起租日', html)

    def test_multiple_fixed_start_options_are_counted(self):
        sems = [semester('Semester 1 2027', terms={'6月':695},
                         fixed_starts={'6月':[[2027,2,4],[2027,2,11],[2027,2,18]]})]
        r = room(sems)
        app.apply_semester_truth(r, sems)
        view = app.semester_views(r)[0]
        self.assertEqual(app._sem_date_parts(view), ('固定起租', '02/04（3天可选）', True))
        self.assertIn('6月固定起租 2027-02-04、2027-02-11、2027-02-18', view['date_str'])

    def test_shortstay_only_button_uses_shortstay_picker_window(self):
        # 学期接口只回 months/dates 片段：短租只有一个 availNowBtn（class ltermSS），
        # 窗口在 available-shortstay-picker-start-date（Central Park 4B / Broadway 4B 实测结构）
        html = ('<ul id="move-in-months"><li class="available-now">'
                '<button type="button" id="availNowBtn" data-22w="" data-44w="" '
                'class="ui-datepicker-trigger ltermSS btn-rev">Choose your date</button></li></ul>'
                '<input id="available-shortstay-picker-start-date" value="2027,1,4">'
                '<input id="available-shortstay-picker-date" value="2027,2,9">')
        dd = app.extract_dates(html)
        self.assertEqual(dd['shortstay_dates'][:1], [(2027,1,4)])
        sems = [semester('Semester 2 2026', terms={'短租':925}, shortstay_dates=[[2027,1,4]])]
        r = room(sems)
        app.apply_semester_truth(r, sems)
        self.assertEqual(app._sem_date_parts(app.semester_views(r)[0]), ('短租起租', '01/04', True))

    def test_shortstay_data_ss_becomes_shortstay_move_in(self):
        months = ('<ul id="move-in-months"><li class="movin-dates">'
                  '<a class="btn white-orange ltermSS btn-rev" data-ss="10/11/2027">November</a></li></ul>')
        dd = app.extract_dates(months)
        self.assertEqual(dd['fixed_starts'].get('短租'), [(2027,11,10)])
        self.assertEqual(dd['shortstay_dates'], [(2027,11,10)])
        sems = [semester('Semester 2 2026', terms={'短租':680}, shortstay_dates=[[2027,11,10]])]
        r = room(sems)
        app.apply_semester_truth(r, sems)
        view = app.semester_views(r)[0]
        self.assertEqual(app._sem_date_parts(view), ('短租起租', '11/10', True))


if __name__ == '__main__':
    unittest.main()
