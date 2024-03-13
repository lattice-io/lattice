import { GithubOutlined, HomeOutlined, LinkedinOutlined, TwitterOutlined } from '@ant-design/icons'
import { DefaultFooter } from '@ant-design/pro-layout'

const authorId = 'BreezeML Inc. All rights reserved.'

export default function GlobalFooter() {
  return (
    <DefaultFooter
      links={[
        {
          key: 'website',
          title: <HomeOutlined />,
          href: 'https://breezeml.ai/',
          blankTarget: true,
        },
        {
          key: 'github',
          title: <GithubOutlined />,
          href: `https://github.com/breezeml`,
          blankTarget: true,
        },
        {
          key: 'linkedin',
          title: <LinkedinOutlined />,
          href: `https://www.linkedin.com/company/breezeml/`,
          blankTarget: true,
        },
        {
          key: 'twitter',
          title: <TwitterOutlined />,
          href: `https://twitter.com/breeze_ml`,
          blankTarget: true,
        },
      ]}
      copyright={`${new Date().getFullYear()} ${authorId}`}
    />
  )
}
