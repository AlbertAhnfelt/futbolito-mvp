import React, { useState } from 'react';
import { Modal, Input, List, Button, Typography, Space, Tag, message } from 'antd';
import { SearchOutlined, TeamOutlined } from '@ant-design/icons';
import { footballApi } from '../services/api';
import type { TeamSearchResult, TeamDetails } from '../types/football';

const { Text } = Typography;

interface TeamSearchModalProps {
  open: boolean;
  onClose: () => void;
  onSelectTeam: (team: TeamDetails) => void;
  title?: string;
}

export const TeamSearchModal: React.FC<TeamSearchModalProps> = ({
  open,
  onClose,
  onSelectTeam,
  title = 'Search Team',
}) => {
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<TeamSearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedTeamId, setSelectedTeamId] = useState<string | null>(null);
  const [loadingTeamDetails, setLoadingTeamDetails] = useState(false);

  const handleSearch = async () => {
    if (!searchQuery || searchQuery.length < 2) {
      message.warning('Please enter at least 2 characters');
      return;
    }

    setLoading(true);
    try {
      const results = await footballApi.searchTeams(searchQuery);
      setSearchResults(results);

      if (results.length === 0) {
        message.info('No teams found');
      }
    } catch (error) {
      console.error('Error searching teams:', error);
      message.error('Failed to search teams. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  const handleSelectTeam = async (teamId: string) => {
    setLoadingTeamDetails(true);
    setSelectedTeamId(teamId);

    try {
      const teamDetails = await footballApi.getTeam(teamId);
      onSelectTeam(teamDetails);
      message.success(`Selected ${teamDetails.name}`);
      handleClose();
    } catch (error) {
      console.error('Error loading team details:', error);
      message.error('Failed to load team details. Please try again.');
    } finally {
      setLoadingTeamDetails(false);
      setSelectedTeamId(null);
    }
  };

  const handleClose = () => {
    setSearchQuery('');
    setSearchResults([]);
    setSelectedTeamId(null);
    onClose();
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      handleSearch();
    }
  };

  return (
    <Modal
      title={title}
      open={open}
      onCancel={handleClose}
      footer={null}
      width={600}
    >
      <Space direction="vertical" style={{ width: '100%' }} size="large">
        <Space.Compact style={{ width: '100%' }}>
          <Input
            placeholder="Enter team name (e.g., Barcelona, Real Madrid)"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            onKeyPress={handleKeyPress}
            prefix={<SearchOutlined />}
            size="large"
          />
          <Button
            type="primary"
            size="large"
            onClick={handleSearch}
            loading={loading}
          >
            Search
          </Button>
        </Space.Compact>

        {searchResults.length > 0 && (
          <List
            dataSource={searchResults}
            loading={loading}
            renderItem={(team) => (
              <List.Item
                key={team.id}
                actions={[
                  <Button
                    type="primary"
                    onClick={() => handleSelectTeam(team.id)}
                    loading={loadingTeamDetails && selectedTeamId === team.id}
                  >
                    Select
                  </Button>,
                ]}
              >
                <List.Item.Meta
                  avatar={<TeamOutlined style={{ fontSize: 24 }} />}
                  title={team.name}
                  description={
                    <Space>
                      {team.country && <Tag color="blue">{team.country}</Tag>}
                      {team.league && <Tag color="green">{team.league}</Tag>}
                    </Space>
                  }
                />
              </List.Item>
            )}
          />
        )}

        {!loading && searchResults.length === 0 && searchQuery && (
          <Text type="secondary" style={{ textAlign: 'center', display: 'block' }}>
            Search for teams by name to get started
          </Text>
        )}
      </Space>
    </Modal>
  );
};
