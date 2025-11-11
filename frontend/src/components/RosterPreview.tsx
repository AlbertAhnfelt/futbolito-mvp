import React from 'react';
import { Card, Table, Typography, Tag, Space } from 'antd';
import { UserOutlined } from '@ant-design/icons';
import type { RosterPlayer } from '../types/football';

const { Title, Text } = Typography;

interface RosterPreviewProps {
  teamName: string;
  roster: RosterPlayer[];
  onImport?: () => void;
}

export const RosterPreview: React.FC<RosterPreviewProps> = ({
  teamName,
  roster,
}) => {
  const columns = [
    {
      title: 'Jersey',
      dataIndex: 'jersey_number',
      key: 'jersey_number',
      width: 80,
      render: (jersey?: string) => (
        <Tag color="blue">{jersey || 'N/A'}</Tag>
      ),
    },
    {
      title: 'Name',
      dataIndex: 'name',
      key: 'name',
      render: (name: string) => (
        <Space>
          <UserOutlined />
          <Text strong>{name}</Text>
        </Space>
      ),
    },
    {
      title: 'Position',
      dataIndex: 'position',
      key: 'position',
      render: (position?: string) => position || '-',
    },
    {
      title: 'Age',
      dataIndex: 'age',
      key: 'age',
      width: 70,
      render: (age?: number) => age || '-',
    },
    {
      title: 'Nationality',
      dataIndex: 'nationality',
      key: 'nationality',
      render: (nationality?: string) => (
        nationality ? <Tag color="green">{nationality}</Tag> : '-'
      ),
    },
  ];

  return (
    <Card
      title={
        <Space>
          <UserOutlined />
          <Title level={5} style={{ margin: 0 }}>
            {teamName} Roster ({roster.length} players)
          </Title>
        </Space>
      }
      style={{ marginTop: 16 }}
    >
      <Table
        dataSource={roster}
        columns={columns}
        rowKey="id"
        pagination={false}
        size="small"
        scroll={{ y: 300 }}
      />
    </Card>
  );
};
