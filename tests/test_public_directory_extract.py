import unittest
from public_directory_extract import visual_text,parse_university_tables


class PublicDirectoryExtractTests(unittest.TestCase):
    def test_rtl_text_keeps_number_order(self):
        self.assertEqual(visual_text('11 هچوک'), 'کوچه 11')
        self.assertEqual(visual_text('یدازآ'),'آزادی')

    def test_split_columns_and_continuation_preserve_source_identity(self):
        rows=[['سردآ','نفلت','هناخوراد','رهش']*2,
              ['سردآ','034123','یدازآ','نامرک','سردآ','034456','رتکد','دنرز'],
              ['11 هچوک',None,None,None,None,None,None,None]]
        result=parse_university_tables([rows],'https://example.invalid/public.pdf')
        self.assertEqual(len(result),2)
        self.assertEqual(result[0]['city'],'زرند')
        self.assertEqual(result[1]['address'],'آدرس کوچه 11')
        self.assertEqual(result[1]['phone'],'034123')
        self.assertEqual(len({row['source_id'] for row in result}),2)
        self.assertTrue(all(row['review_status']=='unverified' and row['customer_id'] is None and row['latitude'] is None for row in result))

    def test_unexpected_layout_is_rejected(self):
        with self.assertRaises(ValueError):parse_university_tables([[['wrong columns']]],'synthetic')
