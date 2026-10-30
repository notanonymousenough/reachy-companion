"""Explicit conversation context, separate from speaker identification."""
import hashlib

MODES = ('normal', 'alice_test')
LEGACY_ALICE_CONTEXT = '\nВ текущей автономной беседе с Алисой '
ALICE_CONTEXT = (
    '\nСейчас включён режим «Тест с Алисой»: твой тестовый собеседник — '
    'соседняя Яндекс Алиса. Это настройка теста, а не распознавание голоса. '
    'Отвечай кратко по существу, обычно одним коротким предложением. '
    'При инициативе задай один полезный вопрос и дождись ответа. '
    'Не проси запускать музыку или управлять устройствами. '
    'Обращение «Алиса, » добавляется при озвучивании автоматически.'
)


def mode_value(value):
    if value is not None and (type(value) is not str or value not in MODES):
        raise ValueError('Unknown conversation mode')
    return value


def mode_prompt(prompt, mode):
    mode_value(mode)
    if mode is None:
        return prompt
    # The installed Windows profile has a losslessly reversible UTF-8/cp1251
    # encoding error. Only repair a clear signature, never guess at plain text.
    if prompt.count('Р') + prompt.count('С') > len(prompt) / 5:
        try:
            repaired = prompt.encode('cp1251').decode('utf-8')
        except (UnicodeEncodeError, UnicodeDecodeError):
            pass
        else:
            if repaired.startswith('Ты Ричи,'):
                prompt = repaired
    # This exact legacy suffix is a test-only role, not the base persona.
    prompt = prompt.split(LEGACY_ALICE_CONTEXT, 1)[0]
    return prompt + (ALICE_CONTEXT if mode == 'alice_test' else '')


def mode_session(session, mode):
    mode_value(mode)
    if mode is None:
        return session
    # Keep bounded keys even for maximum-length externally supplied sessions.
    return 'mode:' + mode + ':' + hashlib.sha256(session.encode()).hexdigest()[:32]


def mode_payload(payload):
    mode = mode_value(payload.get('conversation_mode'))
    if mode is None:
        return payload
    prefix = 'Алиса, ' if mode == 'alice_test' else ''
    if 'speech_address_prefix' in payload and payload['speech_address_prefix'] != prefix:
        raise ValueError('Conversation mode and speech prefix disagree')
    return dict(payload, speech_address_prefix=prefix)
