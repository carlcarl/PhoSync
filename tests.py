import unittest


class PhoSyncTests(unittest.TestCase):

    def test_legal_image_size(self):
        from phosync import legal_image_size
        self.failUnless(legal_image_size('20 bytes') is True)
        self.failUnless(legal_image_size('20 KB') is True)
        self.failUnless(legal_image_size('10 MB') is True)
        self.failUnless(legal_image_size('11 MB') is False)
        self.failUnless(legal_image_size('20 MB') is False)


if __name__ == '__main__':
    unittest.main()
