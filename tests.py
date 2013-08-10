import unittest

PASS = 1
FAIL = 0
size_list = [
    [
        '11 MB',
        '20 MB',
    ],
    [
        '20 bytes',
        '20 KB',
        '10 MB',
    ],
]
mime_list = [
    [
        '',
        'text/plain',
    ],
    [
        'image/jpeg',
        'image/png',
        'image/gif',
        'image/x-ms-bmp',
    ],
]


def test_legal_image_size():
    from phosync import legal_image_size
    for i in size_list[PASS]:
        assert legal_image_size(i) is True
    for i in size_list[FAIL]:
        assert legal_image_size(i) is False


def test_is_image():
    from phosync import is_image
    for i in mime_list[PASS]:
        assert is_image(i) is True
    for i in mime_list[FAIL]:
        assert is_image(i) is False


def check_legal_image(i, j, k):
    from phosync import legal_image
    assert legal_image(
        {
            'size': j,
            'mime_type': k,
        }
    ) is ((i[0] and i[1]) == 1)


def test_legal_image():
    index_list = []
    for i in range(0, 2):
        for j in range(0, 2):
            index_list.append(
                [i, j]
            )
    for i in index_list:
        for j in size_list[i[0]]:
            for k in mime_list[i[1]]:
                yield check_legal_image, i, j, k

# class PhoSyncTests(unittest.TestCase):
#
#     def test_legal_image_size(self):
#         from phosync import legal_image_size
#         for i in self.size_list[PASS]:
#             self.failUnless(legal_image_size(i) is True)
#         for i in self.size_list[FAIL]:
#             self.failUnless(legal_image_size(i) is False)
#
#     def test_is_image(self):
#         from phosync import is_image
#         for i in self.mime_list[PASS]:
#             self.failUnless(is_image(i) is True)
#         for i in self.mime_list[FAIL]:
#             self.failUnless(is_image(i) is False)
#
#     def test_legal_image(self):
#         from phosync import legal_image
#         print('hello')
#         index_list = []
#         for i in range(0, 2):
#             for j in range(0, 2):
#                 index_list.append(
#                     [i, j]
#                 )
#         for i in index_list:
#             for j in self.size_list[i[0]]:
#                 for k in self.mime_list[i[1]]:
#                     yield self.check_legal_image, i, j, k
                    # yield self.check_legal_image, {
                    #     'size': j,
                    #     'mime_type': k,
                    # }, (i[0] and i[1]) == 1
                    # self.failUnless(
                    #     legal_image(
                    #         {
                    #             'size': j,
                    #             'mime_type': k,
                    #         }
                    #     ) is ((i[0] and i[1]) == 1)
                    # )

    # def check_legal_image(self, file_info, is_pass):
    #     from phosync import legal_image
    #     self.failUnless(
    #         legal_image(
    #             file_info
    #         ) is is_pass
    #     )
    # def check_legal_image(self, i, j, k):
    #     from phosync import legal_image
    #     self.failunless(
    #         legal_image(
    #             {
    #                 'size': j,
    #                 'mime_type': k,
    #             }
    #         ) is (i[0] and i[1] == 1)
    #     )


if __name__ == '__main__':
    unittest.main()
