import copy
import json
import math
import unittest
from pathlib import Path
from reachy_companion.emotion_library import catalog, sample
from reachy_companion.expressions import EMOTIONS, plan, spoken_segments
from reachy_companion.speech_motion import GESTURES, pose_step
from reachy_companion.motion_limits import validate_steps

ROOT=Path(__file__).resolve().parents[1]

class RecordedEmotionTests(unittest.TestCase):
    def setUp(self):
        self.settings=json.loads((ROOT/'profiles/friend.json').read_text())['conversation']['expressions']

    def test_every_recorded_curve_and_gesture_stays_bounded(self):
        self.assertEqual(len(EMOTIONS),28)
        self.assertEqual(len(catalog(self.settings['library']['name'])),42)
        for emotion in EMOTIONS:
            for gesture in GESTURES:
                for beat in range(0,32,3):
                    validate_steps([pose_step(self.settings,emotion,gesture,beat)],self.settings)
        for phase in ('neutral','listening','processing','speaking'):
            for variant in range(4):
                validate_steps(plan(self.settings,phase,'confused',variant)['steps'],self.settings)

    def test_curves_change_over_time_and_variant_without_moving_body(self):
        first=sample(self.settings,'joy',.2,0)
        later=sample(self.settings,'joy',1.5,0)
        alternative=sample(self.settings,'joy',.2,1)
        self.assertNotEqual(first,later)
        self.assertNotEqual(first['clip'],alternative['clip'])
        for emotion in EMOTIONS:
            step=pose_step(self.settings,emotion,'auto',2)
            self.assertEqual([step['head_pose'][axis] for axis in ('x','y','z')],[0.,0.,0.])
            self.assertNotIn('body_yaw',step)
        self.assertNotEqual(plan(self.settings,'processing',variant=0)['steps'],plan(self.settings,'processing',variant=1)['steps'])

    def test_llm_can_select_new_emotions_and_only_allowed_gestures(self):
        parts=spoken_segments('<emotion=embarrassed><gesture=bow>Моя ошибка. <emotion=grateful><gesture=shrug>Спасибо за поправку.')
        self.assertEqual([(p['emotion'],p['gesture']) for p in parts],[('embarrassed','bow'),('grateful','shrug')])
        unknown=spoken_segments('<emotion=furious><gesture=execute_shell>нет')[0]
        self.assertEqual((unknown['emotion'],unknown['gesture']),('neutral','auto'))
        for variant in (-1,True,1.5,10001):
            with self.assertRaises(ValueError):plan(self.settings,'processing',variant=variant)

    def test_disable_library_keeps_static_fallback_and_settle_is_stationary(self):
        settings=copy.deepcopy(self.settings);settings['library']['enabled']=False
        self.assertIsNone(sample(settings,'joy',1))
        self.assertEqual(pose_step(self.settings,'joy','settle',0),pose_step(self.settings,'joy','settle',9))
        validate_steps(plan(settings,'speaking','joy')['steps'],settings)
