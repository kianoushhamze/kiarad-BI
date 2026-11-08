import unittest
from public_prospect_discovery import normalize_elements


class PublicProspectTests(unittest.TestCase):
    def test_only_requested_public_business_types_and_stable_identity(self):
        sample={'type':'node','id':1,'lat':30,'lon':57,'tags':{'amenity':'pharmacy','name':'داروخانه'}}
        result=normalize_elements([sample,sample,{'type':'node','id':2,'tags':{'shop':'art'}}])
        self.assertEqual(len(result),1)
        self.assertEqual(result[0]['review_status'],'unverified')
        self.assertIsNone(result[0]['customer_id'])

    def test_way_center_and_missing_name_remain_unknown(self):
        result=normalize_elements([{'type':'way','id':5,'center':{'lat':30,'lon':57},'tags':{'shop':'cosmetics'}}])
        self.assertEqual(result[0]['latitude'],30)
        self.assertIsNone(result[0]['name'])


if __name__=='__main__':
    unittest.main()
