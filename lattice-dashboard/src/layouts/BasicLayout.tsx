/**
 * Ant Design Pro v4 use `@ant-design/pro-layout` to handle Layout.
 *
 * @see You can view component api by: https://github.com/ant-design/ant-design-pro-layout
 */
import { HomeOutlined } from '@ant-design/icons'
import { ConfigProvider } from 'antd'
import enUS from 'antd/es/locale/en_US'
// import GlobalFooter from '@/containers/GlobalFooter'
import ProLayout, { ProSettings } from '@ant-design/pro-layout'
import { useHistory, useLocation } from '@vitjs/runtime'
import { Link } from 'react-router-dom'

const BasicLayout: React.FC = (props) => {
  const location = useLocation()
  const history = useHistory()

  return (
    <ConfigProvider locale={enUS}>
      <ProLayout
        headerTitleRender={(props) => (
          <a href='https://breezeml.ai'>
          </a>
        )}
        {...props}
        onMenuHeaderClick={() => history.push('/')}
        menuItemRender={(menuItemProps, defaultDom) => {
          if (
            menuItemProps.isUrl ||
            !menuItemProps.path ||
            location.pathname === menuItemProps.path
          ) {
            return defaultDom
          }
          return <Link to={menuItemProps.path}>{defaultDom}</Link>
        }}
        // footerRender={() => <GlobalFooter />}
        // waterMarkProps={{
        //   content: 'Vite React',
        //   fontColor: 'rgba(24,144,255,0.15)',
        // }}
        pure
      />
    </ConfigProvider>
  )
}

export default BasicLayout
